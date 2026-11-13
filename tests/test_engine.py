"""python -m unittest discover -s tests -v   (أو pytest)"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "02_nlu_model"))

from assistant_engine import AssistantEngine, detect_need, satisfies, tokens, stem  # noqa: E402
from dense_retrieval import SemanticIndex  # noqa: E402
from llm_generator import Generator, validate_answer  # noqa: E402


class Ev:                                   # دليل مصغّر للاختبار
    def __init__(self, i, text, date="2026-11-06"):
        self.ann_id, self.full_text, self.date = i, text, date


class TextProcessing(unittest.TestCase):
    def test_stem_strips_article_and_plural(self):
        self.assertEqual(stem("الامتحانات"), stem("امتحان") + "") if stem("امتحان") == "امتحان" else None
        self.assertNotIn("ال", tokens("الاسعافات")[0][:2])

    def test_need_detection(self):
        self.assertEqual(detect_need("متى تبدأ الدورة"), "when")
        self.assertEqual(detect_need("كم رسوم الدبلوم"), "price")
        self.assertEqual(detect_need("رقم التواصل"), "phone")
        self.assertEqual(detect_need("وين المركز"), "where")
        self.assertIsNone(detect_need("ما هي الدورات"))
        self.assertNotEqual(detect_need("متى تبدأ دورة مهارات الاتصال"), "phone")

    def test_satisfies(self):
        self.assertTrue(satisfies("when", "تاريخ البدء: الأحد 2/8/2026"))
        self.assertFalse(satisfies("when", "دورة ممتازة جداً"))
        self.assertTrue(satisfies("price", "الرسوم 40,000 ريال"))


class EngineBehaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e = AssistantEngine.from_project(ROOT)

    def route(self, q):
        return self.e.answer(q).route

    def test_gibberish_is_rejected(self):
        self.assertEqual(self.route("asdfgh"), "fallback")
        self.assertEqual(self.route("????"), "fallback")

    def test_chitchat_and_scope(self):
        self.assertEqual(self.route("مرحبا"), "chitchat")
        self.assertEqual(self.route("ما الطقس اليوم"), "out_of_scope")

    def test_grounded_answers_contain_facts(self):
        self.assertIn("40,000", self.e.answer("كم رسوم دبلوم السونار").text)
        self.assertIn("775702470", self.e.answer("رقم التواصل مع المركز").text)

    def test_no_guessing_when_info_missing(self):
        r = self.e.answer("متى يبدأ دبلوم ICDL")
        self.assertEqual(r.route, "partial")
        self.assertIn("ولن أخمّن", r.text)
        self.assertIn("فلن أخمّن", self.e.answer("متى الامتحانات النهائية").text)


class HallucinationGuard(unittest.TestCase):
    EV = [Ev(61, "الدورة مجانية. رسوم الشهادة 2000 ريال. تاريخ البدء 2/8/2026. للتسجيل 775702470")]

    def test_accepts_supported_numbers_and_citation(self):
        self.assertIsNone(validate_answer("رسوم الشهادة 2000 ريال (إعلان 61)", self.EV))

    def test_rejects_invented_number(self):
        self.assertIn("غير مدعوم", validate_answer("الرسوم 5000 ريال", self.EV))
        self.assertIn("غير مدعوم", validate_answer("اتصل على 777123456", self.EV))
        self.assertIn("غير مدعوم", validate_answer("الرسوم 1 ريال", self.EV))

    def test_rejects_links_empty_and_long(self):
        self.assertIsNotNone(validate_answer("زر https://x.com", self.EV))
        self.assertIsNotNone(validate_answer("   ", self.EV))
        self.assertIsNotNone(validate_answer("ا" * 2000, self.EV))

    def test_generator_falls_back_on_bad_output_and_errors(self):
        bad = Generator(lambda s, p: "الرسوم 9999 ريال")
        self.assertIsNone(bad.generate("كم الرسوم", self.EV)[0])
        boom = Generator(lambda s, p: (_ for _ in ()).throw(TimeoutError()))
        text, why = boom.generate("q", self.EV)
        self.assertIsNone(text)
        self.assertIn("فشل المزوّد", why)

    def test_engine_uses_generated_text_only_if_valid(self):
        good = Generator(lambda s, p: "رسوم الدبلوم 40,000 ريال (إعلان 45)")
        e = AssistantEngine.from_project(ROOT, generator=good)
        r = e.answer("كم رسوم دبلوم السونار")
        self.assertTrue(r.generated)
        self.assertIn("المصدر", r.text)
        bad = Generator(lambda s, p: "الرسوم 1 ريال فقط")
        r2 = AssistantEngine.from_project(ROOT, generator=bad).answer("كم رسوم دبلوم السونار")
        self.assertFalse(r2.generated)
        self.assertIn("40,000", r2.text)            # رجع للرد الاستخراجي الآمن


class SemanticIndexTest(unittest.TestCase):
    def test_cosine_ranking_with_fake_encoder(self):
        vecs = {"a": [1, 0], "b": [0, 1], "q": [0.9, 0.1]}

        def enc(texts, is_query):
            out = np.array([vecs["q"] if is_query else vecs[t] for t in texts], dtype=np.float32)
            return out / np.linalg.norm(out, axis=1, keepdims=True)

        idx = SemanticIndex([{"id": 1, "text": "a"}, {"id": 2, "text": "b"}], encoder=enc)
        self.assertEqual(idx.top("q", 1)[0][0], 1)


if __name__ == "__main__":
    unittest.main()
