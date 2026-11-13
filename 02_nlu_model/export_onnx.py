"""Export to ONNX, verify numerically, optional INT8 quantization, golden tests."""
import argparse
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

from nlu_common import CNNBiLSTM, encode, load_json, save_json, preprocess


def load_model(art: Path):
    cfg = load_json(art / "config.json")
    model = CNNBiLSTM(**{k: v for k, v in cfg.items() if k != "max_len"})
    model.load_state_dict(torch.load(art / "model.pt", map_location="cpu"))
    return model.eval(), cfg


def softmax(x):
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--art", default="artifacts")
    ap.add_argument("--quantize", action="store_true")
    a = ap.parse_args()
    art = Path(a.art)

    model, cfg = load_model(art)
    vocab = load_json(art / "vocab.json")
    labels = load_json(art / "labels.json")
    onnx_path = art / "intent_model.onnx"

    dummy = torch.ones(1, cfg["max_len"], dtype=torch.long)
    kwargs = dict(input_names=["input_ids"], output_names=["logits"],
                  dynamic_axes={"input_ids": {0: "batch"}, "logits": {0: "batch"}},
                  opset_version=17)
    try:
        torch.onnx.export(model, dummy, str(onnx_path), dynamo=False, **kwargs)
    except TypeError:  # older torch has no `dynamo` argument
        torch.onnx.export(model, dummy, str(onnx_path), **kwargs)
    print(f"exported {onnx_path}  ({onnx_path.stat().st_size/1024:.0f} KB)")

    samples = ["متى الامتحانات النهائية", "كيف ادفع الرسوم", "السلام عليكم",
               "وين اشوف جدول المحاضرات", "اعطني وصفة كبسة", "كم باقي على التخرج",
               "شكرا لك", "كيف اقدم على منحة دراسية", "نسيت كلمة المرور",
               "ما هي اخر الاعلانات"]
    ids = np.array([encode(s, vocab, cfg["max_len"]) for s in samples], dtype=np.int64)

    with torch.no_grad():
        ref = model(torch.from_numpy(ids)).numpy()

    def check(path, name, strict):
        sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        got = sess.run(None, {"input_ids": ids})[0]
        diff = np.abs(ref - got).max()
        same = (ref.argmax(1) == got.argmax(1)).mean()
        print(f"[{name}] max|diff|={diff:.2e}  argmax agreement={same:.0%}")
        if strict:
            assert diff < 1e-3, "ONNX output differs from PyTorch!"
        return got

    got = check(onnx_path, "fp32", strict=True)

    if a.quantize:
        from onnxruntime.quantization import QuantType, quantize_dynamic
        q_path = art / "intent_model.int8.onnx"
        quantize_dynamic(str(onnx_path), str(q_path), weight_type=QuantType.QInt8)
        print(f"quantized {q_path} ({q_path.stat().st_size/1024:.0f} KB)")
        check(q_path, "int8", strict=False)

    # Golden tests: lets the Dart implementation prove it matches Python exactly
    probs = softmax(got)
    save_json([{
        "input": s, "normalized": preprocess(s), "ids": ids[i].tolist(),
        "intent": labels[int(probs[i].argmax())],
        "confidence": round(float(probs[i].max()), 4),
    } for i, s in enumerate(samples)], art / "golden_tests.json")
    print("wrote golden_tests.json")


if __name__ == "__main__":
    main()
