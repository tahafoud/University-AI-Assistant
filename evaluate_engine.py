"""تقييم موثوقية المحرك: python evaluate_engine.py
يطبع (1) دقة المصنّف على مجموعة التحقق مع المعايرة، (2) اختبارات سلوكية للقرار والمنطق."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assistant_engine import AssistantEngine, P_CONFIDENT  # noqa: E402
from data import build_splits  # noqa: E402

eng = AssistantEngine.from_project()

# ---- 1) المصنّف وحده: الدقة والمعايرة على seeds غير مستخدمة في التدريب
labels, _, val = build_splits(seed=42)
P = np.array([[p for _, p in sorted(((l, p) for l, p in eng.model.predict(t)), key=lambda x: labels.index(x[0]))]
              for t, _ in val])
y = np.array([l for _, l in val])
pred = P.argmax(1)
conf = P.max(1)
print(f"دقة المصنّف على التحقق: {(pred == y).mean():.3f}  (n={len(y)})")
ece = 0.0
for lo in np.arange(0, 1, 0.1):
    m = (conf > lo) & (conf <= lo + 0.1)
    if m.any():
        ece += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
print(f"خطأ المعايرة ECE: {ece:.3f}  (الأقل أفضل)")
m = conf >= P_CONFIDENT
print(f"عند عتبة {P_CONFIDENT}: تغطية {m.mean():.2f} ودقة على المُجاب {(pred[m] == y[m]).mean():.3f}\n")

# ---- 2) اختبارات سلوكية: (السؤال، المسار المتوقع، نص يجب أن يظهر في الرد أو None)
CASES = [
    ("مرحبا", "chitchat", None),
    ("شكرا لك", "chitchat", None),
    ("asdfgh", "fallback", None),
    ("????", "fallback", None),
    ("ما الطقس اليوم", "out_of_scope", None),
    ("اريد حجز طيارة", "out_of_scope", None),
    ("كيف احسب معدلي التراكمي", "kb", None),
    ("كم نسبة الغياب المسموحة", "kb", None),
    ("ما هي اخر الاخبار", "grounded", "أحدث"),
    ("اريد الفحص المجاني للحوامل", "grounded", "الحوامل"),
    ("متى تبدأ دورة الإسعافات الأولية", "grounded", "الاحد"),
    ("كم رسوم دورة الاسعافات الاولية", "grounded", "2000"),
    ("كم رسوم دبلوم السونار", "grounded", "40,000"),
    ("رقم التواصل مع المركز", "grounded", "775702470"),
    ("متى يبدأ دبلوم ICDL", "partial", "ولن أخمّن"),      # الإعلان موجود لكن بلا موعد -> لا تخمين
    ("متى الامتحانات النهائية", "kb", "فلن أخمّن"),         # لا إعلان بجدول -> صدق لا قالب
]
ok = 0
for q, route, must in CASES:
    r = eng.answer(q)
    good = r.route == route and (must is None or must in r.text)
    ok += good
    print(("✅" if good else "❌"), f"{q:38s} → {r.route:12s} ({r.reason})")
print(f"\nنجح {ok}/{len(CASES)} من الاختبارات السلوكية")
sys.exit(0 if ok == len(CASES) else 1)
