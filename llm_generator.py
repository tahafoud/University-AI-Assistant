"""
llm_generator.py - طبقة توليد اختيارية (RAG) مع حارس ضد الهلوسة.

الفكرة: المحرك يسترجع الإعلانات أولاً (دليل)، ثم يطلب من نموذج لغوي أن يصوغ ردّاً
طبيعياً *من هذا الدليل فقط*. بعدها يفحص الحارس الرد: أي رقم/هاتف/سعر/تاريخ في الرد
غير موجود حرفياً في الدليل ⇒ يُرفض الرد ويُستخدم الرد الاستخراجي الآمن.

المزوّدات (بلا مكتبات إضافية، urllib فقط):
  none       : معطّل (الافتراضي) — يعمل المشروع كله بلا إنترنت.
  ollama     : نموذج محلي على جهازك (http://localhost:11434) — خصوصية كاملة.
  anthropic  : Claude عبر الـAPI (يحتاج ANTHROPIC_API_KEY).

الإعداد عبر متغيرات البيئة: LLM_PROVIDER, LLM_MODEL, OLLAMA_URL, ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, Sequence

NLU_DIR = Path(__file__).resolve().parent / "02_nlu_model"
if str(NLU_DIR) not in sys.path:
    sys.path.insert(0, str(NLU_DIR))
from arabic_text import clean_arabic_text

SYSTEM_PROMPT = (
    "أنت مساعد جامعي. أجب بالعربية وبإيجاز (حتى 4 جمل) اعتماداً على الإعلانات المرفقة فقط.\n"
    "قواعد صارمة:\n"
    "1) لا تذكر أي رقم أو تاريخ أو سعر أو رقم هاتف أو اسم غير موجود حرفياً في الإعلانات.\n"
    "2) إن لم تحتوِ الإعلانات على الجواب فقل: «لا يذكر الإعلان ذلك» ولا تخمّن.\n"
    "3) اذكر رقم الإعلان بين قوسين مثل (إعلان 61) عند كل معلومة.\n"
    "4) التواريخ النسبية (غداً/الأسبوع القادم) نسبةً ليوم نشر الإعلان، وضّح ذلك."
)

_NUM = re.compile(r"\d[\d,.]*\d|\d")
_AMOUNT = re.compile(r"(\d[\d,.]*)\s*(?:ريال|دولار|الف|%)")
_URL = re.compile(r"https?://|www\.", re.I)


def build_prompt(query: str, evidence: Sequence, max_chars: int = 1400) -> str:
    blocks: List[str] = []
    for e in evidence:
        body = (e.full_text or "")[:max_chars]
        blocks.append(f"[إعلان {e.ann_id} | نُشر {e.date}]\n{body}")
    return "الإعلانات:\n\n" + "\n\n---\n\n".join(blocks) + f"\n\nسؤال الطالب: {query}\nالجواب:"


def _numbers(text: str) -> set:
    t = clean_arabic_text(text, level="nlp")
    return {n.strip(",.").replace(",", "") for n in _NUM.findall(t)}


def validate_answer(answer: str, evidence: Sequence, max_len: int = 900) -> Optional[str]:
    """يعيد None إذا كان الرد سليماً، وإلا سبب الرفض."""
    a = (answer or "").strip()
    if not a:
        return "رد فارغ"
    if len(a) > max_len:
        return "رد طويل جداً"
    if _URL.search(a):
        return "رابط غير مسموح"
    ev_text = " ".join(e.full_text or "" for e in evidence)
    ev_nums = {x.replace(",", "") for x in _numbers(ev_text)}
    ev_ids = {str(e.ann_id) for e in evidence}
    ev_amounts = {m.strip(",.").replace(",", "")
                  for m in _AMOUNT.findall(clean_arabic_text(ev_text, level="nlp"))}
    a_norm = clean_arabic_text(a, level="nlp")
    # (1) أي مبلغ (رقم + ريال/دولار/%) يجب أن يطابق مبلغاً مذكوراً في الدليل
    for m in _AMOUNT.findall(a_norm):
        if m.strip(",.").replace(",", "") not in ev_amounts:
            return f"مبلغ غير مدعوم بالدليل: {m}"
    # (2) أي رقم من 3 خانات فأكثر (هاتف/سنة/سعر) يجب أن يكون في الدليل؛ أرقام الإعلانات المُستشهد بها مسموحة
    for n in _numbers(a):
        n = n.replace(",", "")
        if len(n) >= 3 and n not in ev_ids and n not in ev_nums:
            return f"رقم غير مدعوم بالدليل: {n}"
    return None


class Generator:
    """transport: دالة (system, prompt) -> نص. تُحقن في الاختبارات بدل الشبكة."""

    def __init__(self, transport: Callable[[str, str], str]):
        self.transport = transport

    def generate(self, query: str, evidence: Sequence):
        """يعيد (نص, سبب_الرفض). النص None إذا رُفض أو فشل الاتصال."""
        if not evidence:
            return None, "لا يوجد دليل"
        try:
            raw = self.transport(SYSTEM_PROMPT, build_prompt(query, evidence))
        except Exception as ex:                       # شبكة/مهلة/مفتاح
            return None, f"فشل المزوّد: {type(ex).__name__}"
        why = validate_answer(raw, evidence)
        return (None, why) if why else (raw.strip(), None)


def _post(url: str, payload: dict, headers: dict, timeout: float = 30.0) -> dict:
    hdrs = {"User-Agent": "UniversityAssistant/1.0", **headers}
    try:
        import requests
        r = requests.post(url, json=payload, headers=hdrs, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except ImportError:
        req = urllib.request.Request(url, json.dumps(payload).encode("utf-8"), hdrs, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:      # noqa: S310 (عنوان ثابت من الإعداد)
            return json.loads(r.read().decode("utf-8"))


def _ollama(model: str, base: str):
    def call(system: str, prompt: str) -> str:
        out = _post(base.rstrip("/") + "/api/chat",
                    {"model": model, "stream": False, "options": {"temperature": 0.1},
                     "messages": [{"role": "system", "content": system},
                                  {"role": "user", "content": prompt}]},
                    {"Content-Type": "application/json"})
        return out["message"]["content"]
    return call


def _groq(model: str, key: str):
    def call(system: str, prompt: str) -> str:
        out = _post("https://api.groq.com/openai/v1/chat/completions",
                    {"model": model, "messages": [{"role": "system", "content": system},
                                                  {"role": "user", "content": prompt}],
                     "temperature": 0.1, "max_tokens": 400},
                    {"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        return out["choices"][0]["message"]["content"]
    return call


def _anthropic(model: str, key: str):
    def call(system: str, prompt: str) -> str:
        out = _post("https://api.groq.com/openai/v1/chat/completions" if "groq" in model else "https://api.anthropic.com/v1/messages",
                    {"model": model, "max_tokens": 400, "temperature": 0.1, "system": system,
                     "messages": [{"role": "user", "content": prompt}]},
                    {"Content-Type": "application/json", "x-api-key": key,
                     "anthropic-version": "2023-06-01"})
        return "".join(b.get("text", "") for b in out.get("content", []))
    return call


def from_env() -> Optional[Generator]:
    prov = os.getenv("LLM_PROVIDER", "none").lower()
    if prov == "groq":
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY غير مضبوط")
        return Generator(_groq(os.getenv("LLM_MODEL", "qwen/qwen3.8-27b"), key))
    if prov == "ollama":
        return Generator(_ollama(os.getenv("LLM_MODEL", "qwen2.5:3b"),
                                 os.getenv("OLLAMA_URL", "http://localhost:11434")))
    if prov == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY غير مضبوط")
        return Generator(_anthropic(os.getenv("LLM_MODEL", "claude-haiku-5-5"), key))
    return None
