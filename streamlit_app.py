import json
import random
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
import streamlit as st

from datetime import datetime

# Setup paths
BASE_DIR = Path(__file__).resolve().parent
NLU_DIR = BASE_DIR / "02_nlu_model"
ART_DIR = NLU_DIR / "artifacts"
INGEST_DIR = BASE_DIR / "01_telegram_ingest"
ANNOUNCEMENTS_FILE = INGEST_DIR / "data" / "announcements.json"
KNOWLEDGE_FILE = BASE_DIR / "03_flutter_app" / "knowledge.json"
UNANSWERED_FILE = BASE_DIR / "unanswered_queries.json"

# Semantic synonyms map for smart announcements matching
SYNONYMS = {
    "امتحان": ["اختبار", "فاينل", "ميدتيرم", "امتحانات", "اختبارات", "نهائي"],
    "اختبار": ["امتحان", "فاينل", "ميدتيرم", "امتحانات", "اختبارات"],
    "فاينل": ["امتحان", "اختبار", "نهائي"],
    "ميد": ["نصفي", "امتحان", "اختبار"],
    "رسوم": ["مصاريف", "اقساط", "سداد", "تسديد", "مالية", "تكلفة"],
    "دفع": ["سداد", "تسديد", "رسوم", "مصاريف", "بنك"],
    "تسجيل": ["حذف", "اضافة", "مقررات", "شعبة", "شعب", "بوابة"],
    "منحة": ["اعفاء", "تخفيض", "خصم", "مساعدة", "تفوق"],
    "غياب": ["حرمان", "عذر", "طبي", "انذار"],
    "نتائج": ["درجات", "علامات", "معدل", "تظلم"],
    "تخرج": ["خريج", "وثيقة", "شهادة", "اخلاء طرف"],
    "دكتور": ["استاذ", "محاضر", "مرشد", "عميد"],
}

sys.path.append(str(NLU_DIR))
from arabic_text import clean_arabic_text

# Page Configuration
st.set_page_config(
    page_title="المساعد الجامعي الذكي - تجربة النموذج",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Arabic Styling
st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
    
    html, body, [class*="css"], .stMarkdown, p, div, span, h1, h2, h3, h4, h5, h6, input, textarea, button {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }
    
    .stChatMessage {
        direction: rtl !important;
        text-align: right !important;
        border-radius: 12px;
        padding: 10px;
        margin-bottom: 8px;
    }
    
    .intent-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.82rem;
        font-weight: 700;
        margin-bottom: 6px;
    }
    .badge-high { background-color: #d1fae5; color: #065f46; border: 1px solid #a7f3d0; }
    .badge-mid  { background-color: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
    .badge-low  { background-color: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
    
    .announcement-card {
        background-color: #f8fafc;
        border-right: 4px solid #3b82f6;
        border-radius: 8px;
        padding: 12px;
        margin-top: 10px;
        font-size: 0.9rem;
    }
    .announcement-date {
        color: #64748b;
        font-size: 0.75rem;
        margin-bottom: 4px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Friendly Arabic names for intents
INTENT_TITLES = {
    "greeting": "ترحيب وتحية 👋",
    "goodbye_thanks": "شكر ووداع 🙏",
    "registration": "تسجيل المقررات والحذف والإضافة 📝",
    "exam_schedule": "مواعيد وجدول الامتحانات 📅",
    "grades_results": "النتائج والمعدل التراكمي 📊",
    "tuition_fees": "الرسوم والمصاريف الجامعية 💳",
    "scholarships": "المنح والدعم المالي 🎁",
    "graduation_requirements": "متطلبات وشروط التخرج 🎓",
    "academic_procedures": "الإجراءات الأكاديمية والوثائق 📄",
    "lecture_schedule": "جدول المحاضرات والقاعات 🏛️",
    "latest_announcements": "أحدث الأخبار والإعلانات 📢",
    "library_services": "خدمات المكتبة والكتب 📖",
    "contact_support": "الدعم الفني والتواصل 📞",
    "attendance_absence": "الحضور والغياب والأعذار ⏱️",
    "housing_transport": "السكن الجامعي والمواصلات 🚌",
    "student_activities": "الأنشطة والأندية الطلابية ⚽",
    "internships_jobs": "التدريب الميداني والتوظيف 💼",
    "campus_services": "مرافق وخدمات الحرم الجامعي 🏥",
    "course_info": "معلومات وتوصيف المقررات 📘",
    "out_of_scope": "خارج النطاق الجامعي 🛑",
    "unknown": "غير مؤكد / بحاجة لتوضيح ❓",
}


@st.cache_resource
def load_nlu_model():
    """Load ONNX runtime session and metadata."""
    cfg = json.loads((ART_DIR / "config.json").read_text(encoding="utf-8"))
    vocab = json.loads((ART_DIR / "vocab.json").read_text(encoding="utf-8"))
    labels = json.loads((ART_DIR / "labels.json").read_text(encoding="utf-8"))

    # Load quantized model if exists, otherwise normal onnx
    onnx_file = ART_DIR / "intent_model.int8.onnx"
    if not onnx_file.exists():
        onnx_file = ART_DIR / "intent_model.onnx"

    session = ort.InferenceSession(str(onnx_file), providers=["CPUExecutionProvider"])
    return session, cfg, vocab, labels


@st.cache_data
def load_knowledge():
    """Load knowledge base answers."""
    if KNOWLEDGE_FILE.exists():
        return json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8"))
    return {"intents": {}, "suggestions": []}


@st.cache_data
def load_announcements():
    """Load synced Telegram announcements."""
    if ANNOUNCEMENTS_FILE.exists():
        try:
            return json.loads(ANNOUNCEMENTS_FILE.read_text(encoding="utf-8")).get(
                "items", []
            )
        except Exception:
            return []
    return []


def predict_intent(text: str, session, cfg, vocab, labels, threshold=0.60):
    """Classify user intent using the ONNX model."""
    norm = clean_arabic_text(text, level="nlp")
    pad, unk = 0, 1
    max_len = cfg["max_len"]

    ids = [vocab.get(c, unk) for c in norm][:max_len]
    ids += [pad] * (max_len - len(ids))

    logits = session.run(None, {"input_ids": np.array([ids], dtype=np.int64)})[0][0]
    p = np.exp(logits - logits.max())
    p /= p.sum()

    top_indices = np.argsort(-p)
    top_intent = labels[top_indices[0]]
    top_score = float(p[top_indices[0]])

    best_intent = top_intent if top_score >= threshold else "unknown"
    ranked = [(labels[i], float(p[i])) for i in top_indices[:5]]

    return best_intent, top_score, ranked


def log_unanswered(query: str, confidence: float, top_ranked: list):
    """Save questions that were unknown or had low confidence for active learning."""
    try:
        entries = []
        if UNANSWERED_FILE.exists():
            entries = json.loads(UNANSWERED_FILE.read_text(encoding="utf-8"))
        entries.append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "query": query,
            "confidence": round(confidence, 3),
            "top_predictions": [(name, round(score, 3)) for name, score in top_ranked[:3]]
        })
        UNANSWERED_FILE.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def search_announcements(query: str, announcements, limit=2):
    """Find announcements matching user query with semantic synonyms expansion."""
    if not announcements:
        return []

    raw_words = [w for w in clean_arabic_text(query, level="nlp").split() if len(w) > 2]
    if not raw_words:
        return announcements[:limit]

    # Expand words with synonyms
    expanded_words = set(raw_words)
    for w in raw_words:
        for root, syns in SYNONYMS.items():
            if root in w:
                expanded_words.update(syns)

    scored = []
    for a in announcements:
        text = a.get("text", "") or ""
        norm_text = clean_arabic_text(text, level="nlp")
        score = sum(1 for w in expanded_words if w in norm_text)
        if score > 0:
            scored.append((score, a))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:limit]]


@st.cache_resource
def get_engine():
    sys.path.insert(0, str(BASE_DIR))
    import os
    from assistant_engine import AssistantEngine
    from llm_generator import from_env
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        pass
    sem = "auto" if os.getenv("SEM_ENABLE") == "1" else None
    return AssistantEngine.from_project(BASE_DIR, generator=from_env(), semantic=sem)


# Initialize resources
session, cfg, vocab, labels = load_nlu_model()
knowledge = load_knowledge()
announcements = load_announcements()

# ==========================================
# Sidebar: Model Telemetry & Controls
# ==========================================
with st.sidebar:
    st.markdown("### ⚙️ إعدادات النموذج")
    threshold = st.slider(
        "عتبة الثقة (Threshold)",
        min_value=0.30,
        max_value=0.95,
        value=0.60,
        step=0.05,
        help="إذا كانت ثقة النموذج أقل من هذه النسبة، يعتبر السؤال غير معروف (Unknown).",
    )

    st.markdown("---")
    st.markdown("### 📊 إحصائيات النظام")
    col1, col2 = st.columns(2)
    col1.metric("عدد النوايا", len(labels))
    col2.metric("الإعلانات", len(announcements))

    st.markdown("---")
    st.markdown("### 💡 أسئلة سريعة للتجربة:")
    suggestions = knowledge.get("suggestions", [
        "متى الامتحانات النهائية؟",
        "كيف أسجل المواد للفصل القادم؟",
        "كم الرسوم الدراسية وطريقة الدفع؟",
        "ما هي آخر الإعلانات؟",
        "ما نسبة الغياب المسموحة؟",
        "كيف أقدم على منحة تفوق؟",
        "وين العيادة الطبية في الجامعة؟",
        "السلام عليكم ورحمة الله",
    ])

    for q in suggestions[:7]:
        if st.button(q, key=f"btn_{q}", use_container_width=True):
            st.session_state["user_input_override"] = q

    st.markdown("---")
    with st.expander("📥 أسئلة للتعلم المستمر (Active Learning)"):
        if UNANSWERED_FILE.exists():
            try:
                unans = json.loads(UNANSWERED_FILE.read_text(encoding="utf-8"))
                st.caption(f"تم تسجيل {len(unans)} سؤالاً غير مفهوم للمراجعة.")
                for item in reversed(unans[-5:]):
                    st.markdown(f"• **{item['query']}** <br><span style='color:gray;font-size:0.75rem'>{item['timestamp']}</span>", unsafe_allow_html=True)
            except Exception:
                st.write("لا توجد أسئلة مسجلة.")
        else:
            st.write("لا توجد أسئلة غير مفهومة مسجلة بعد.")

    if st.button("🗑️ مسح المحادثة", use_container_width=True):
        st.session_state["messages"] = []
        st.rerun()

# ==========================================
# Main Chat Area
# ==========================================
st.title("🎓 المساعد الجامعي الذكي (تجربة الذكاء الاصطناعي)")
st.caption(
    "واجهة تفاعلية لاختبار نموذج تصنيف النوايا (ONNX) وربطه مع إعلانات تيليجرام الحية."
)

if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {
            "role": "assistant",
            "content": "أهلاً بك يا طالبنا العزيز! 👋 أنا المساعد الجامعي الذكي، اسألني عن التسجيل، الامتحانات، الرسوم، أو آخر إعلانات الجامعة.",
            "intent": "greeting",
            "confidence": 1.0,
            "ranked": [],
        }
    ]

# Render chat history
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and msg.get("intent"):
            intent = msg["intent"]
            conf = msg.get("confidence", 0.0)
            title = INTENT_TITLES.get(intent, intent)

            badge_class = (
                "badge-high"
                if conf >= 0.8
                else ("badge-mid" if conf >= 0.6 else "badge-low")
            )
            st.markdown(
                f'<span class="intent-badge {badge_class}">النية: {title} ({conf*100:.1f}%) · المسار: {msg.get("route", "-")}</span>',
                unsafe_allow_html=True,
            )

        st.markdown(msg["content"])

        # Display attached related announcements if any
        if msg.get("announcements"):
            st.markdown("**📌 إعلانات مرتبطة من قناة الجامعة:**")
            for a in msg["announcements"]:
                date_str = a.get("date", "")[:10]
                full_text = a.get("text") or "إعلان مصوّر"
                media_rel = a.get("media")
                media_file = (INGEST_DIR / media_rel) if media_rel else None

                st.markdown(
                    f"""
                    <div class="announcement-card">
                        <div class="announcement-date">📅 تاريخ الإعلان: {date_str} (رقم {a.get('id')})</div>
                        <div style="white-space: pre-wrap; line-height: 1.8; margin-top: 6px;">{full_text}</div>
                    </div>
                """,
                    unsafe_allow_html=True,
                )
                if media_file and media_file.exists():
                    st.image(str(media_file), caption=f"مرفق الإعلان رقم {a.get('id')}", use_container_width=True)

# User input
user_query = st.chat_input("اكتب سؤالك هنا (مثال: متى مواعيد الامتحانات النهائية؟)...")
if "user_input_override" in st.session_state:
    user_query = st.session_state.pop("user_input_override")

if user_query:
    # 1. Add user message
    st.session_state["messages"].append({"role": "user", "content": user_query})

    # 2. المحرك الجديد: حارس مدخلات ← مصنّف معايَر ← استرجاع مؤسَّس ← قرار صريح
    import assistant_engine as AE
    AE.P_CONFIDENT = threshold
    reply = get_engine().answer(user_query)
    best_intent, top_score, ranked = reply.intent, reply.confidence, reply.ranked
    bot_response = reply.text
    matched_announcements = [
        {"id": e.ann_id, "date": e.date, "text": e.title, "media": e.media}
        for e in reply.evidence if e.media
    ][:2]
    if reply.route in ("fallback", "clarify"):
        log_unanswered(user_query, top_score, ranked)

    # 3. (تم دمجها داخل المحرك)
    # 4. Save response to chat
    st.session_state["messages"].append(
        {
            "role": "assistant",
            "content": bot_response,
            "intent": best_intent,
            "route": reply.route,
            "reason": reply.reason,
            "generated": reply.generated,
            "confidence": top_score,
            "ranked": ranked,
            "announcements": matched_announcements,
        }
    )

    st.rerun()

