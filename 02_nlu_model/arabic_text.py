"""
arabic_text.py - Arabic text cleaning / normalization.

Two levels:
  * "display": light cleanup, text stays readable for showing in the app.
  * "nlp"    : aggressive normalization for search & the intent classifier
               (unify hamza forms, remove diacritics, unify digits, ...).
"""
import re
import unicodedata

# ---- regexes -------------------------------------------------------------
_TASHKEEL = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_TATWEEL = "\u0640"
# zero-width chars, bidi controls, BOM
_INVISIBLE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_URL = re.compile(r"(https?://\S+|www\.\S+|t\.me/\S+)", re.IGNORECASE)
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF"
    "\U0000FE0F\U0000200D]"
)
_REPEAT = re.compile(r"(.)\1{2,}")           # "ششششكرا" -> "ششكرا"
_NON_WORD = re.compile(r"[^\u0621-\u063A\u0641-\u064Aa-zA-Z0-9\s]")
_SPACES = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES = re.compile(r"\n{3,}")

# Arabic-Indic (٠-٩) and Persian (۰-۹) digits -> Western digits
_DIGITS = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_DIGITS.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})

_PUNCT = {ord("،"): ",", ord("؛"): ";", ord("؟"): "?"}


def clean_arabic_text(
    text: str,
    level: str = "display",
    unify_ta_marbuta: bool = True,
    unify_hamza_on_carrier: bool = True,
    keep_urls: bool = False,
) -> str:
    """Clean Arabic text. level = 'display' | 'nlp'."""
    if not text:
        return ""

    # NFKC also converts Arabic presentation forms (ﻻ, ﻷ, ﺑ ...) which OCR
    # engines often emit, into the normal base letters.
    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE.sub("", text)
    text = text.replace(_TATWEEL, "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    if level == "display":
        text = _SPACES.sub(" ", text)
        text = "\n".join(line.strip() for line in text.split("\n"))
        return _BLANK_LINES.sub("\n\n", text).strip()

    # ---------------- level == "nlp" ----------------
    text = _TASHKEEL.sub("", text)
    text = _EMOJI.sub(" ", text)
    text = text.translate(_DIGITS)
    text = text.translate(_PUNCT)
    if not keep_urls:
        text = _URL.sub(" ", text)

    # unify alef forms: أ إ آ ٱ -> ا
    text = re.sub("[إأآٱ]", "ا", text)
    # alef maqsura -> ya
    text = text.replace("ى", "ي")
    if unify_ta_marbuta:
        text = text.replace("ة", "ه")
    if unify_hamza_on_carrier:
        text = text.replace("ؤ", "و").replace("ئ", "ي")

    text = _REPEAT.sub(r"\1\1", text)
    text = _NON_WORD.sub(" ", text)
    text = _SPACES.sub(" ", text.replace("\n", " "))
    return text.strip().lower()


if __name__ == "__main__":
    sample = "أُعلِنَتْ نتـــائجُ الامتحاناتِ النهائية ٢٠٢٦/١١/٠٥ 🎉🎉 رابط: https://t.me/x"
    print("display:", clean_arabic_text(sample, "display"))
    print("nlp    :", clean_arabic_text(sample, "nlp"))
