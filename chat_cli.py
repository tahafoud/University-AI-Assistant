"""محادثة من سطر الأوامر:  python chat_cli.py [--debug]
LLM اختياري:   set LLM_PROVIDER=ollama  (أو anthropic مع ANTHROPIC_API_KEY)
دلالي اختياري: set SEM_ENABLE=1   (يتطلب sentence-transformers)"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from assistant_engine import AssistantEngine  # noqa: E402
from llm_generator import from_env  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="اعرض المسار والسبب والنوايا")
    a = ap.parse_args()
    eng = AssistantEngine.from_project(
        ROOT, generator=from_env(), semantic="auto" if os.getenv("SEM_ENABLE") == "1" else None)
    print("المساعد الجامعي — اكتب سؤالك (exit للخروج)")
    while True:
        try:
            q = input("\n❓ ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in ("exit", "quit", "خروج"):
            break
        if not q:
            continue
        r = eng.answer(q)
        print("\n" + r.text)
        if a.debug:
            print(f"\n[route={r.route} intent={r.intent} p={r.confidence:.2f} generated={r.generated}"
                  f" | {r.reason}{' | llm: ' + r.llm_note if r.llm_note else ''}]")


if __name__ == "__main__":
    main()
