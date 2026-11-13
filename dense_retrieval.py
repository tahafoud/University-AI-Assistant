"""
dense_retrieval.py - استرجاع دلالي اختياري (تضمينات).

يفهم المعنى لا الكلمات: "فحص الحوامل" ~ "متابعة النساء والولادة". يُستخدم في المحرك لأمرين فقط:
  1) إعادة ترتيب مرشّحي BM25 (لا يستطيع إنشاء مطابقة زائفة بمفرده).
  2) اقتراح إعلان قريب عند الفشل، فقط إذا تجاوز التشابه SEM_MIN.

النموذج الافتراضي: intfloat/multilingual-e5-small (يدعم العربية، ~120MB، يعمل على CPU).
التثبيت:  pip install sentence-transformers
ملاحظة: عتبة SEM_MIN تتغير من نموذج لآخر؛ اضبطها بتجربة أسئلة حقيقية (evaluate_engine --semantic).
"""
from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

MODEL_NAME = os.getenv("SEM_MODEL", "intfloat/multilingual-e5-small")
SEM_MIN = float(os.getenv("SEM_MIN", "0.80"))


def default_encoder(model_name: str = MODEL_NAME) -> Callable[[List[str], bool], np.ndarray]:
    from sentence_transformers import SentenceTransformer     # استيراد متأخر: اختياري

    model = SentenceTransformer(model_name)

    def enc(texts: List[str], is_query: bool) -> np.ndarray:
        pre = "query: " if is_query else "passage: "            # صيغة E5
        return model.encode([pre + t for t in texts], normalize_embeddings=True,
                            batch_size=16, show_progress_bar=False)
    return enc


class SemanticIndex:
    def __init__(self, announcements: Sequence[dict],
                 encoder: Optional[Callable[[List[str], bool], np.ndarray]] = None):
        self.enc = encoder or default_encoder()
        self.ids = [a.get("id", i) for i, a in enumerate(announcements)]
        docs = [((a.get("text") or "")[:1200]) or "إعلان مصوّر" for a in announcements]
        self.mat = np.asarray(self.enc(docs, False), dtype=np.float32) if docs else np.zeros((0, 1))

    def scores(self, query: str) -> Dict[int, float]:
        if not len(self.ids):
            return {}
        q = np.asarray(self.enc([query], True), dtype=np.float32)[0]
        sims = self.mat @ q                                   # الأشعة مُطبَّعة ⇒ cosine
        return {i: float(s) for i, s in zip(self.ids, sims)}

    def top(self, query: str, k: int = 3):
        sc = self.scores(query)
        return sorted(sc.items(), key=lambda x: -x[1])[:k]


def try_build(announcements: Sequence[dict]) -> Optional[SemanticIndex]:
    """يعيد None بصمت إذا لم تكن المكتبة/النموذج متاحين (المحرك يعمل بدونها)."""
    try:
        return SemanticIndex(announcements)
    except Exception:
        return None
