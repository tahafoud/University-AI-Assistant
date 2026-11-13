"""Reference inference (exactly what the Flutter app will do).  python predict_onnx.py "متى الامتحانات" """
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort

from arabic_text import clean_arabic_text
import json

ART = Path("artifacts")
PAD, UNK = 0, 1
THRESHOLD = 0.60  # tune from train.py's threshold table

vocab = json.loads((ART / "vocab.json").read_text(encoding="utf-8"))
labels = json.loads((ART / "labels.json").read_text(encoding="utf-8"))
cfg = json.loads((ART / "config.json").read_text(encoding="utf-8"))
sess = ort.InferenceSession(str(ART / "intent_model.onnx"),
                            providers=["CPUExecutionProvider"])


def predict(text: str):
    norm = clean_arabic_text(text, level="nlp")                 # 1) normalize
    ids = [vocab.get(c, UNK) for c in norm][: cfg["max_len"]]    # 2) chars -> ids
    ids += [PAD] * (cfg["max_len"] - len(ids))                   # 3) pad
    logits = sess.run(None, {"input_ids": np.array([ids], dtype=np.int64)})[0][0]
    p = np.exp(logits - logits.max()); p /= p.sum()              # 4) softmax
    top = np.argsort(-p)[:3]
    best = labels[top[0]] if p[top[0]] >= THRESHOLD else "unknown"
    return best, [(labels[i], round(float(p[i]), 3)) for i in top]


if __name__ == "__main__":
    for q in sys.argv[1:] or ["متى تبدأ الاختبارات النهائية؟"]:
        print(q, "->", predict(q))
