"""
assistant_engine.py - محرك المساعد الجامعي (نسخة أكثر موثوقية ومنطقية)

بدل أن يعتمد الرد على "نية واحدة + قالب عشوائي"، يمر السؤال بطبقات:

  1. حارس المدخلات   : يرفض الكلام العشوائي/غير العربي بدل أن يصنّفه بثقة 96%.
  2. المصنّف (ONNX)   : احتمالات معايَرة (temperature) + هامش بين أول نيتين.
  3. استرجاع مؤسَّس   : BM25 مع تجذيع عربي خفيف ومرادفات على إعلانات القناة،
                         ويعيد أفضل الأسطر المطابقة للسؤال (دليل) لا أول 160 حرفاً.
  4. قرار صريح        : grounded | kb | clarify | chitchat | out_of_scope | fallback
                         وكل رد يحمل route وسبباً (للتشخيص والاختبار).

المبدأ: لا يجيب بمعلومة إلا إذا كان لها سند (إعلان فعلي أو قاعدة معرفة)،
وإذا لم يجد يقول ذلك صراحة بدل قالب عام يوحي بأنه يعرف.
"""
from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import onnxruntime as ort

BASE = Path(__file__).resolve().parent
NLU_DIR = BASE / "02_nlu_model"
sys.path.insert(0, str(NLU_DIR))
from arabic_text import clean_arabic_text  # noqa: E402

PAD, UNK = 0, 1

# ---------------------------------------------------------------- الإعدادات
TEMPERATURE = 1.2          # معايرة على مجموعة التحقق (انظر evaluate_engine.py)
P_CONFIDENT = 0.60         # أدنى احتمال لقبول النية
MARGIN_MIN = 0.25          # أدنى فرق بين أول نيتين وإلا نطلب توضيحاً
P_CHITCHAT = 0.80          # التحية/الشكر تُقبل فقط بثقة عالية وجملة قصيرة
CHITCHAT_MAX_TOKENS = 6
REL_STRONG = 0.60          # صلة الإعلان بالسؤال لنجيب منه مباشرة
REL_RELATED = 0.40         # صلة كافية لعرضه كـ"إعلان ذو صلة"
OOV_MAX = 0.35             # نسبة الحروف غير المعروفة للنموذج قبل اعتبار المدخل عشوائياً
NON_TOPIC = {"greeting", "goodbye_thanks", "out_of_scope"}

SYNONYMS = {
    "امتحان": ["اختبار", "فاينل", "ميدتيرم", "نهائي", "نصفي"],
    "اختبار": ["امتحان", "فاينل", "ميدتيرم"],
    "رسوم": ["مصاريف", "اقساط", "سداد", "تسديد", "تكلفه", "اجور", "مبلغ"],
    "دفع": ["سداد", "تسديد", "رسوم"],
    "تسجيل": ["التحاق", "قبول", "اشتراك", "تقديم", "حجز"],
    "منحه": ["اعفاء", "تخفيض", "خصم", "مساعده", "تفوق"],
    "غياب": ["حرمان", "عذر", "انذار"],
    "نتايج": ["درجات", "علامات", "معدل", "تظلم"],
    "تخرج": ["خريج", "وثيقه", "شهاده"],
    "دوره": ["تدريب", "ورشه", "برنامج", "دبلوم", "كورس"],
    "تدريب": ["دوره", "ورشه", "تاهيل"],
    "فحص": ["معاينه", "كشف", "طبي", "علاج", "عياده"],
    "مجاني": ["مجانا", "بدون", "مجان"],
    "وظيفه": ["توظيف", "عمل", "فرصه"],
}

STOP = set(
    "في من الي علي عن مع هل ما ماذا متي كيف كم اين وين هو هي هذا هذه ذلك تلك الذي التي "
    "ان اني انا انت نحن لو او ثم قد لقد كان كانت يكون ليس لا لم لن بعد قبل عند حتي كل بعض "
    "اريد ابغي ابي اود عايز ممكن لو سمحت الان اي ايش وش شو هناك يوجد فيه فيها له لها لي لنا "
    "بس جدا اخر اخبار خبر جديد جديده اعلانات اعلان".split()
)

_AR = re.compile(r"[\u0621-\u064A]")
_LATIN = re.compile(r"[a-z]")
_TOKEN = re.compile(r"[\u0621-\u064A]+|[a-z]+|\d+")

_PREFIXES = ("وبال", "وال", "بال", "كال", "فال", "لل", "ال", "وب", "ول", "و", "ب", "ل", "ف")
_SUFFIXES = ("ات", "ون", "ين", "ان", "ها", "هم", "كم", "نا", "ي", "ه")


def stem(tok: str) -> str:
    """تجذيع عربي خفيف (يُطبَّق على نص مُطبَّع ة->ه، ى->ي)."""
    if not _AR.search(tok) or len(tok) <= 3:
        return tok
    for p in _PREFIXES:
        if tok.startswith(p) and len(tok) - len(p) >= 3:
            tok = tok[len(p):]
            break
    for s in _SUFFIXES:
        if tok.endswith(s) and len(tok) - len(s) >= 3:
            tok = tok[: -len(s)]
            break
    return tok


_NOISE = re.compile(r"#\S+|\[\d{1,2}/\d{1,2}[^\]]*\][^:]{0,40}:|\d{7,}")


def tokens(text: str) -> List[str]:
    """هاشتاقات وأرقام الهواتف وبادئات رسائل الواتساب لا تدخل في الفهرسة."""
    norm = clean_arabic_text(_NOISE.sub(" ", text), level="nlp")
    out = (stem(t) for t in _TOKEN.findall(norm) if t not in STOP)
    return [t for t in out if t not in STOP]


SYNONYMS.update({"اسجل": ["تسجيل"], "سجل": ["تسجيل"], "تسجيل": ["اسجل", "سجل"]})
NEED_WORDS = {stem(clean_arabic_text(w, level="nlp")) for w in (
    "تبدأ يبدأ موعد مواعيد تاريخ كم رقم واتساب هاتف تلفون سعر تكلفة رسوم مبلغ وين اين موقع عنوان مكان").split()}

_SYN_STEM: Dict[str, List[str]] = {}
for _k, _v in SYNONYMS.items():
    _SYN_STEM.setdefault(stem(_k), []).extend(stem(x) for x in _v)
    for _x in _v:
        _SYN_STEM.setdefault(stem(_x), []).append(stem(_k))


# ------------------------------------------------ نوع المعلومة التي يطلبها السؤال
_NEED_RX = {
    "when": re.compile(
        r"\d{1,2}\s*[/\-.]\s*\d{1,2}|\d{1,2}\s*:\s*\d{2}|\b20\d\d\b|"
        r"السبت|الاحد|الاثنين|الثلاثاء|الاربعاء|الخميس|الجمعه|يناير|فبراير|مارس|ابريل|مايو|يونيو|"
        r"يوليو|اغسطس|سبتمبر|اكتوبر|نوفمبر|ديسمبر|الاسبوع القادم|الاسبوع المقبل|غدا|بدايه من|ابتداء من"),
    "price": re.compile(r"ريال|دولار|\$|مجان|\d[\d,.]*\s*(الف|ريال|ر\.?ي)|(رسوم|سعر|تكلف|مبلغ).{0,20}\d"),
    "phone": re.compile(r"\d{7,}"),
    "where": re.compile(r"عنوان|شارع|جوار|بجانب|الموقع"),
}


def detect_need(query: str) -> Optional[str]:
    """ماذا يريد السائل بالضبط؟ موعد / سعر / رقم تواصل (أو لا شيء محدد)."""
    q = clean_arabic_text(query, level="nlp")
    if re.search(r"رقم|واتساب|واتس|تلفون|هاتف|اتواصل|للتواصل|اتصل بكم", q):
        return "phone"
    if re.search(r"\b(وين|اين|موقع|عنوان|مكان|موقعه|مكانه)\b", q):
        return "where"
    if re.search(r"\bكم\b.*(رسوم|سعر|تكلف|مبلغ|اجر|قيمه)|(سعر|تكلفه|ثمن)", q) or re.search(r"(رسوم|سعر).*\bكم\b", q):
        return "price"
    if re.search(r"\b(متي|امتي|موعد|مواعيد|تاريخ|تبدا|يبدا|ينتهي|ايام)\b", q):
        return "when"
    return None


def satisfies(need: Optional[str], text: str) -> bool:
    if need is None:
        return True
    return bool(_NEED_RX[need].search(clean_arabic_text(text, level="nlp")))


# ------------------------------------------------------------------ البيانات
@dataclass
class Evidence:
    ann_id: int
    date: str
    title: str
    lines: List[str]
    relevance: float
    media: Optional[str] = None
    full_text: str = ""
    answers_need: bool = True
    proximity: int = 99          # أقرب مسافة (بالأسطر) بين المعلومة المطلوبة وكلمة الموضوع


@dataclass
class Reply:
    text: str
    route: str                      # grounded|kb|clarify|chitchat|out_of_scope|fallback
    intent: str
    confidence: float
    reason: str
    ranked: List[Tuple[str, float]] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    generated: bool = False                # هل صاغ النموذج اللغوي النص (وجاز الحارس)؟
    llm_note: str = ""                      # سبب رفض الصياغة إن رُفضت


# ------------------------------------------------------------------- الاسترجاع
class AnnouncementIndex:
    """BM25 على جذور الكلمات + تغطية موزونة بـ IDF لقياس الصلة (0..1)."""

    K1, B = 1.4, 0.75

    def __init__(self, items: Sequence[dict]):
        self.items = list(items)
        self.docs = [tokens(a.get("text") or "") for a in self.items]
        self.tf = [self._count(d) for d in self.docs]
        n = max(len(self.docs), 1)
        self.avgdl = (sum(len(d) for d in self.docs) / n) or 1.0
        df: Dict[str, int] = {}
        for d in self.tf:
            for t in d:
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        self.max_idf = math.log(1 + (n + 0.5) / 1.5)

    @staticmethod
    def _count(toks: Sequence[str]) -> Dict[str, int]:
        d: Dict[str, int] = {}
        for t in toks:
            d[t] = d.get(t, 0) + 1
        return d

    def _expand(self, q: List[str]) -> Dict[str, float]:
        """وزن 1.0 للكلمة الأصلية و0.6 للمرادف."""
        w: Dict[str, float] = {}
        for t in q:
            w[t] = 1.0
        for t in q:
            for s in _SYN_STEM.get(t, []):
                w.setdefault(s, 0.6)
        return w

    def search(self, query: str, limit: int = 3, extra: Sequence[str] = (),
               need: Optional[str] = None) -> List[Evidence]:
        q = tokens(query)
        if not q or not self.items:
            return []
        weights = self._expand(q)
        for k in extra:                       # كلمات النية تدعم الترتيب فقط بوزن ضعيف
            weights.setdefault(stem(clean_arabic_text(k, level="nlp")), 0.3)

        # أقصى تغطية ممكنة = مجموع وزن كلمات السؤال الأصلية (لا المرادفات)
        qt = [t for t in q if t not in NEED_WORDS] or q      # الموضوع لا كلمات السؤال العامة
        denom = sum(self.idf.get(t, self.max_idf) for t in qt) or 1.0
        out: List[Tuple[float, int]] = []
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i]) or 1
            bm = 0.0
            for t, w in weights.items():
                f = tf.get(t, 0)
                if f:
                    bm += w * self.idf.get(t, 0.0) * f * (self.K1 + 1) / (
                        f + self.K1 * (1 - self.B + self.B * dl / self.avgdl))
            # تغطية حقيقية: كلمات السؤال الأصلية فقط (أو مرادفها إن غابت الأصلية)
            matched = 0.0
            for t in qt:
                if tf.get(t):
                    matched += self.idf.get(t, self.max_idf)
                else:
                    alt = [s for s in _SYN_STEM.get(t, []) if tf.get(s)]
                    if alt:
                        matched += 0.6 * self.idf.get(t, self.max_idf)
            rel = min(matched / denom, 1.0)
            if rel > 0:
                out.append((rel * 100 + bm * 0.01, i))
        out.sort(key=lambda x: (round(x[0], 3), self.items[x[1]].get("date", "")), reverse=True)

        res: List[Evidence] = []
        seen: List[set] = []
        for score, i in out:
            sig = set(self.docs[i])
            # إعلانات مكررة (نفس النص منشور أكثر من مرة): نُبقي الأحدث فقط
            if any(sig and len(sig & o) / len(sig | o) > 0.8 for o in seen):
                continue
            seen.append(sig)
            rel = min(score / 100.0, 1.0)
            res.append(self._evidence(self.items[i], q, weights, rel, need))
            if len(res) >= limit:
                break
        return res

    SPECIFIC_IDF = 1.2    # كلمة أندر من هذا تُعدّ "محددة" (مثل اسعاف/سونار) لا عامة (مثل دورة/مركز)

    def has_specific(self, query: str) -> bool:
        qt = [t for t in tokens(query) if t not in NEED_WORDS]
        return any(self.idf.get(t, self.max_idf) >= self.SPECIFIC_IDF for t in qt)

    def _evidence(self, a: dict, q: List[str], weights: Dict[str, float], rel: float,
                  need: Optional[str] = None) -> Evidence:
        """يختار الأسطر الأدل على الجواب. إن طُلب موعد/سعر/رقم فلا يُعدّ الإعلان
        مجيباً إلا إذا وُجد سطر يحوي المعلومة وبجواره (±1) كلمة من موضوع السؤال."""
        text = (a.get("text") or "").strip()
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        title = lines[0] if lines else "إعلان مصوّر"
        ltoks = [set(tokens(ln)) for ln in lines]
        topic = {t for t in q if t not in NEED_WORDS}
        spec = {t for t in topic if self.idf.get(t, self.max_idf) >= self.SPECIFIC_IDF}
        topic = spec or topic                       # الكلمات العامة (دورة، مركز) لا تثبت أن السطر عن موضوعنا
        topic |= {x for t in list(topic) for x in _SYN_STEM.get(t, []) if self.idf.get(x, 0) >= self.SPECIFIC_IDF}

        def dist(i: int) -> int:
            """مسافة السطر i عن أقرب سطر فيه كلمة من الموضوع (نافذة 6 أسطر للخلف و1 للأمام)
            حتى لا تُنسب معلومة من إعلان مدموج إلى موضوع إعلان آخر في النص نفسه."""
            if not topic:
                return 0
            ds = [abs(i - j) for j in range(i - 6, i + 2) if 0 <= j < len(lines) and ltoks[j] & topic]
            return min(ds) if ds else 99

        chosen: List[int] = []
        answers, prox = True, 99
        if need:
            hits = sorted(((dist(i), i) for i, ln in enumerate(lines) if satisfies(need, ln)),
                          key=lambda x: (x[0], x[1]))
            hits = [h for h in hits if h[0] <= 6]
            answers = bool(hits)
            if hits:
                prox = hits[0][0]
            chosen = [i for _, i in hits[:3]]
        if not chosen:
            scored = []
            for i, ln in enumerate(lines[1:], start=1):
                sc = sum(weights[t] for t in ltoks[i] if t in weights)
                if sc > 0:
                    scored.append((sc, i))
            scored.sort(key=lambda x: -x[0])
            chosen = [i for _, i in scored[:3]]
        out_lines, seen = [], {title}
        for i in sorted(set(chosen)):
            ln = lines[i]
            if ln not in seen:
                seen.add(ln)
                out_lines.append(ln)
        return Evidence(
            ann_id=a.get("id", 0),
            date=(a.get("date") or "")[:10],
            title=title,
            lines=out_lines,
            relevance=rel,
            media=a.get("media"),
            full_text=text,
            answers_need=answers,
            proximity=prox,
        )


# ------------------------------------------------------------------- المصنّف
class IntentModel:
    def __init__(self, art_dir: Path = NLU_DIR / "artifacts", temperature: float = TEMPERATURE):
        self.cfg = json.loads((art_dir / "config.json").read_text(encoding="utf-8"))
        self.vocab = json.loads((art_dir / "vocab.json").read_text(encoding="utf-8"))
        self.labels = json.loads((art_dir / "labels.json").read_text(encoding="utf-8"))
        f = art_dir / "intent_model.int8.onnx"
        if not f.exists():
            f = art_dir / "intent_model.onnx"
        self.sess = ort.InferenceSession(str(f), providers=["CPUExecutionProvider"])
        self.T = temperature

    def oov_ratio(self, norm: str) -> float:
        chars = [c for c in norm if not c.isspace()]
        if not chars:
            return 1.0
        return sum(1 for c in chars if c not in self.vocab) / len(chars)

    def logits(self, text: str) -> np.ndarray:
        norm = clean_arabic_text(text, level="nlp")
        ids = [self.vocab.get(c, UNK) for c in norm][: self.cfg["max_len"]]
        ids += [PAD] * (self.cfg["max_len"] - len(ids))
        return self.sess.run(None, {"input_ids": np.array([ids], dtype=np.int64)})[0][0]

    def predict(self, text: str) -> List[Tuple[str, float]]:
        z = self.logits(text) / self.T
        p = np.exp(z - z.max())
        p /= p.sum()
        order = np.argsort(-p)
        return [(self.labels[i], float(p[i])) for i in order]


# -------------------------------------------------------------------- المحرك
INTENT_TITLES = {
    "registration": "تسجيل المقررات", "exam_schedule": "مواعيد الامتحانات",
    "grades_results": "النتائج والمعدل", "tuition_fees": "الرسوم الدراسية",
    "scholarships": "المنح", "graduation_requirements": "متطلبات التخرج",
    "academic_procedures": "الإجراءات الأكاديمية", "lecture_schedule": "جدول المحاضرات",
    "latest_announcements": "أحدث الإعلانات", "library_services": "خدمات المكتبة",
    "contact_support": "التواصل والدعم", "attendance_absence": "الحضور والغياب",
    "housing_transport": "السكن والمواصلات", "student_activities": "الأنشطة الطلابية",
    "internships_jobs": "التدريب والتوظيف", "campus_services": "خدمات الحرم الجامعي",
    "course_info": "معلومات المقررات",
}


class AssistantEngine:
    def __init__(self, knowledge: dict, announcements: Sequence[dict],
                 model: Optional[IntentModel] = None, student_name: str = "عزيزي الطالب",
                 generator=None, semantic=None):
        self.kb = knowledge
        self.model = model or IntentModel()
        self.index = AnnouncementIndex(announcements)
        self.announcements = sorted(announcements, key=lambda a: a.get("date", ""), reverse=True)
        self.name = student_name
        self._turn = 0
        self.generator = generator      # llm_generator.Generator أو None
        self.semantic = semantic        # dense_retrieval.SemanticIndex أو None

    @classmethod
    def from_project(cls, base: Path = BASE, **kw) -> "AssistantEngine":
        kb = json.loads((base / "03_flutter_app" / "knowledge.json").read_text(encoding="utf-8"))
        ann = json.loads((base / "01_telegram_ingest" / "data" / "announcements.json")
                         .read_text(encoding="utf-8")).get("items", [])
        if kw.get("semantic") == "auto":               # بناء الفهرس الدلالي إن توفرت المكتبة
            from dense_retrieval import try_build
            kw["semantic"] = try_build(ann)
        return cls(kb, ann, **kw)

    # -- أدوات التنسيق
    @staticmethod
    def _fmt_date(d: str) -> str:
        try:
            return datetime.fromisoformat(d).strftime("%Y/%m/%d")
        except ValueError:
            return d

    def _kb_answer(self, intent: str) -> Optional[str]:
        k = self.kb.get("intents", {}).get(intent)
        if not k or not k.get("answers"):
            return None
        ans = k["answers"]
        self._turn += 1
        return ans[(self._turn - 1) % len(ans)].replace("{name}", self.name)   # تناوب حتمي لا عشوائي

    def _render_evidence(self, ev: Evidence) -> str:
        body = "\n".join(f"  ▫️ {ln}" for ln in ev.lines) if ev.lines else ""
        head = f"📌 **{ev.title}**\n🗓 {self._fmt_date(ev.date)} — إعلان رقم {ev.ann_id}"
        note = ""
        if re.search(r"غدا|غداً|الاسبوع القادم|الأسبوع القادم|اليوم", " ".join(ev.lines)):
            note = "\n  ⚠️ التواريخ النسبية (غداً/الأسبوع القادم) محسوبة من يوم نشر الإعلان."
        return head + ("\n" + body if body else "") + note

    # -- القرار
    def answer(self, query: str) -> Reply:
        r = self._decide(query)
        if self.generator and r.route in ("grounded", "partial", "kb") and r.evidence:
            ev = [e for e in r.evidence if e.full_text][:2]
            text, why = self.generator.generate(query, ev)
            if text:
                src = "، ".join(f"إعلان {e.ann_id} ({self._fmt_date(e.date)})" for e in ev)
                r.text = f"{text}\n\n🔎 المصدر: {src}"
                r.generated = True
            else:
                r.llm_note = why or ""          # نبقي الرد الاستخراجي الآمن
        return r

    def _decide(self, query: str) -> Reply:
        norm = clean_arabic_text(query, level="nlp")
        toks = tokens(query)
        ranked = self.model.predict(query)
        top, p1 = ranked[0]
        p2 = ranked[1][1]
        margin = p1 - p2
        top_ranked = [(l, round(p, 3)) for l, p in ranked[:5]]

        # 1) حارس المدخلات
        if not _AR.search(norm) or self.model.oov_ratio(norm) > OOV_MAX or len(norm) < 2:
            return self._fallback(query, ranked, "مدخل غير مفهوم (حروف غير عربية/عشوائية)", top_ranked)

        # 2) تحية/شكر: فقط بثقة عالية وجملة قصيرة (لا نبتلع سؤالاً حقيقياً)
        if top in ("greeting", "goodbye_thanks") and p1 >= P_CHITCHAT and len(norm.split()) <= CHITCHAT_MAX_TOKENS:
            a = self._kb_answer(top)
            if a:
                return Reply(a, "chitchat", top, p1, "تحية/شكر بثقة عالية", top_ranked)

        # 3) استرجاع من الإعلانات (مستقل عن النموذج)
        extra = self.kb.get("intents", {}).get(top, {}).get("keywords", []) if top not in NON_TOPIC else []
        need = detect_need(query)
        found = self.index.search(query, limit=10, extra=extra, need=need) if toks else []
        sem = self.semantic.scores(query) if (self.semantic and toks) else {}
        if sem:                                 # إعادة ترتيب فقط؛ لا يُنشئ مطابقة جديدة
            found.sort(key=lambda e: -(e.relevance + 0.25 * sem.get(e.ann_id, 0.0)))
        # الإعلان "يجيب" فقط إذا طابق الموضوع وحوى المعلومة المطلوبة (موعد/سعر/رقم)
        answering = sorted((e for e in found if e.relevance >= REL_STRONG and e.answers_need),
                           key=lambda e: (e.proximity, -e.relevance))
        best_rel = answering[0].relevance if answering else 0.0

        generic_news = top == "latest_announcements" and need is None and not self.index.has_specific(query)
        if answering and top not in ("greeting", "goodbye_thanks") and not generic_news:
            strong = [e for e in answering if e.proximity <= answering[0].proximity + 2][:2]
            if need in ("price", "when"):          # جواب واحد أدق من قائمة قد تخلط موضوعين
                strong = strong[:1]
            lead = {"when": "هذه المواعيد المذكورة في إعلانات الجامعة:",
                    "price": "هذه الأسعار/الرسوم المذكورة في إعلانات الجامعة:",
                    "phone": "أرقام التواصل المذكورة في الإعلانات:",
                    "where": "العنوان/المكان المذكور في الإعلانات:"}.get(
                need, "وجدت في إعلانات الجامعة ما يخص سؤالك:")
            txt = lead + "\n\n" + "\n\n".join(self._render_evidence(e) for e in strong)
            return Reply(txt, "grounded", top, p1,
                         f"إعلان مطابق بصلة {best_rel:.2f} (النية: {top} {p1:.2f})",
                         top_ranked, strong)

        confident = p1 >= P_CONFIDENT and margin >= MARGIN_MIN
        topical = [e for e in found if e.relevance >= REL_STRONG]

        # 3.5) الموضوع موجود في إعلان لكن المعلومة المطلوبة غائبة ← نقول ذلك صراحة ولا نخمّن
        if need and topical and not answering and (not confident or top in NON_TOPIC):
            e = topical[0]
            missing = {"when": "الموعد", "price": "السعر", "phone": "رقم التواصل", "where": "العنوان"}[need]
            phone = re.search(r"\d{9}", e.full_text)
            txt = (f"وجدت إعلاناً عن هذا الموضوع لكنه لا يذكر {missing} بوضوح، ولن أخمّن:\n\n"
                   + self._render_evidence(e))
            if phone and need != "phone":
                txt += f"\n\n📞 للاستفسار عن {missing}: {phone.group(0)}"
            return Reply(txt, "partial", top, p1, f"موضوع مطابق بلا {missing}", top_ranked, [e])

        # 4) خارج النطاق
        if top == "out_of_scope" and confident:
            return Reply(self._kb_answer("out_of_scope") or "", "out_of_scope", top, p1,
                         "خارج النطاق بثقة", top_ranked)

        # 5) آخر الإعلانات
        if top == "latest_announcements" and p1 >= P_CONFIDENT and generic_news:
            latest = self.announcements[:3]
            evs = [self.index._evidence(a, [], {}, 1.0) for a in latest]
            txt = "هذه أحدث إعلانات القناة:\n\n" + "\n\n".join(self._render_evidence(e) for e in evs)
            return Reply(txt, "grounded", top, p1, "طلب آخر الأخبار", top_ranked, evs)

        # 6) نية واضحة ← قاعدة المعرفة + إعلانات ذات صلة حقيقية فقط
        if confident and top not in NON_TOPIC:
            k = self.kb.get("intents", {}).get(top, {})
            base = self._kb_answer(top) or ""
            related = [e for e in found if e.relevance >= REL_RELATED and e.answers_need][:2]
            if k.get("retrieve") and related:
                txt = base + "\n\n📌 إعلانات ذات صلة:\n\n" + "\n\n".join(self._render_evidence(e) for e in related)
            elif k.get("retrieve"):
                missing = {"when": "الموعد", "price": "السعر", "phone": "رقم التواصل", "where": "العنوان"}.get(need)
                note = k.get("no_match") or "لا يوجد إعلان محفوظ بهذا الخصوص حالياً."
                if missing and found:
                    note = f"وجدت إعلانات قريبة من الموضوع لكن لا أحد منها يذكر {missing} بوضوح، فلن أخمّن. " + note
                txt = base + "\n\nℹ️ " + note
            else:
                txt = base
            return Reply(txt, "kb", top, p1, f"نية واضحة p={p1:.2f} هامش={margin:.2f}", top_ranked, related)

        # 7) غموض حقيقي بين نيتين موضوعيتين ← اسأل الطالب بدل التخمين
        cands = [(l, p) for l, p in ranked[:3] if l not in NON_TOPIC and p >= 0.15]
        if len(cands) >= 2 and p1 >= 0.30:
            opts = " أم ".join(f"**{INTENT_TITLES.get(l, l)}**" for l, _ in cands[:2])
            txt = f"سؤالك يحتمل أكثر من معنى — هل تقصد {opts}؟ اكتب سؤالك بتفصيل أكثر لأجيبك بدقة."
            rel = [e for e in found if e.relevance >= REL_RELATED and e.answers_need][:1]
            if rel:
                txt += "\n\nوربما يفيدك هذا الإعلان:\n\n" + self._render_evidence(rel[0])
            return Reply(txt, "clarify", top, p1, f"غموض: {cands[0][0]} vs {cands[1][0]}", top_ranked, rel)

        return self._fallback(query, ranked, f"ثقة منخفضة p={p1:.2f}", top_ranked, found)

    def _fallback(self, query, ranked, reason, top_ranked, found=None) -> Reply:
        fb = self.kb.get("fallback", {})
        txt = fb.get("answer", "لم أفهم سؤالك تماماً، حاول إعادة صياغته.")
        found = found if found is not None else self.index.search(query, limit=2)
        found = [e for e in found if e.relevance >= REL_STRONG]
        rel = [e for e in found if e.relevance >= REL_RELATED][:2]
        if rel and len(rel[0].lines) >= 0 and rel[0].relevance >= REL_STRONG:
            txt += "\n\n" + fb.get("related_prefix", "ربما تفيدك هذه الإعلانات:") + "\n\n" + \
                   "\n\n".join(self._render_evidence(e) for e in rel)
        if not rel and self.semantic and not reason.startswith("مدخل غير مفهوم"):
            from dense_retrieval import SEM_MIN
            hit = self.semantic.top(query, 1)
            if hit and hit[0][1] >= SEM_MIN:           # اقتراح دلالي حذر، وليس جواباً
                a = next((x for x in self.announcements if x.get("id") == hit[0][0]), None)
                if a:
                    ev = self.index._evidence(a, [], {}, hit[0][1])
                    rel = [ev]
                    txt += "\n\nأقرب إعلان من حيث المعنى (قد لا يطابق سؤالك تماماً):\n\n" + self._render_evidence(ev)
        return Reply(txt, "fallback", "unknown", ranked[0][1], reason, top_ranked, rel)
