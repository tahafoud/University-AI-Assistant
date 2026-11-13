"""
ocr_engine.py - Arabic OCR for Telegram announcement images (EasyOCR + OpenCV).

Pipeline:
  image -> resize -> grayscale -> denoise -> CLAHE contrast
        -> (auto-invert if dark background) -> adaptive threshold
  OCR is run on several variants and the best result (by confidence*length)
  is kept, because designed posters behave differently under thresholding.
"""
import logging
import math
from statistics import median
from typing import Dict, List, Tuple

import cv2
import numpy as np

log = logging.getLogger("ocr")


class ArabicOCR:
    def __init__(self, gpu: bool = False, langs=("ar", "en")):
        self.gpu = gpu
        self.langs = list(langs)
        self._reader = None  # lazy: loading models takes a few seconds

    @property
    def reader(self):
        if self._reader is None:
            import easyocr
            log.info("Loading EasyOCR models %s (gpu=%s)...", self.langs, self.gpu)
            self._reader = easyocr.Reader(self.langs, gpu=self.gpu)
        return self._reader

    # ------------------------------------------------------------------
    # Preprocessing
    # ------------------------------------------------------------------
    @staticmethod
    def preprocess(img_bgr: np.ndarray) -> Dict[str, np.ndarray]:
        h, w = img_bgr.shape[:2]
        longest = max(h, w)
        # Small images: upscale (thin Arabic strokes need pixels).
        # Huge images: downscale (speed, memory).
        if longest < 1600:
            scale = min(2.0, 1600 / longest)
            img_bgr = cv2.resize(img_bgr, None, fx=scale, fy=scale,
                                 interpolation=cv2.INTER_CUBIC)
        elif longest > 3200:
            scale = 3200 / longest
            img_bgr = cv2.resize(img_bgr, None, fx=scale, fy=scale,
                                 interpolation=cv2.INTER_AREA)

        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, None, h=10,
                                            templateWindowSize=7,
                                            searchWindowSize=21)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)

        # Light text on dark background -> invert so text is dark
        if enhanced.mean() < 110:
            enhanced = 255 - enhanced

        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, blockSize=31, C=15,
        )
        # Remove tiny specks without eating Arabic dots
        binary = cv2.medianBlur(binary, 3)

        _, otsu = cv2.threshold(enhanced, 0, 255,
                                cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return {"original": img_bgr, "enhanced": enhanced,
                "adaptive": binary, "otsu": otsu}

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------
    def _run(self, image: np.ndarray) -> List[Tuple[list, str, float]]:
        return self.reader.readtext(image, detail=1, paragraph=False,
                                    text_threshold=0.6, low_text=0.35)

    @staticmethod
    def _score(results) -> float:
        # Reward both confidence and amount of text recovered.
        return sum(conf * len(text.strip()) for _, text, conf in results)

    @staticmethod
    def _assemble(results) -> str:
        """Group boxes into lines (by y), order each line right-to-left."""
        if not results:
            return ""
        items = []
        for box, text, _ in results:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            items.append({
                "text": text.strip(),
                "x": (min(xs) + max(xs)) / 2,
                "y": (min(ys) + max(ys)) / 2,
                "h": max(ys) - min(ys),
            })
        tol = max(8.0, median(i["h"] for i in items) * 0.6)
        items.sort(key=lambda i: i["y"])

        lines, current = [], [items[0]]
        for it in items[1:]:
            if abs(it["y"] - current[-1]["y"]) <= tol:
                current.append(it)
            else:
                lines.append(current)
                current = [it]
        lines.append(current)

        out = []
        for line in lines:
            line.sort(key=lambda i: -i["x"])  # right -> left for Arabic
            out.append(" ".join(i["text"] for i in line if i["text"]))
        return "\n".join(out)

    def read_array(self, img_bgr: np.ndarray, min_conf: float = 0.25) -> str:
        variants = self.preprocess(img_bgr)
        best_text, best_score, best_name = "", -1.0, ""
        for name in ("enhanced", "adaptive", "original"):
            try:
                results = self._run(variants[name])
            except Exception as exc:  # noqa: BLE001
                log.warning("OCR variant %s failed: %s", name, exc)
                continue
            results = [r for r in results if r[2] >= min_conf]
            score = self._score(results)
            log.debug("variant=%s score=%.1f boxes=%d", name, score, len(results))
            if score > best_score:
                best_score, best_name = score, name
                best_text = self._assemble(results)
        log.info("OCR best variant: %s (score %.1f)", best_name, max(best_score, 0))
        return best_text

    def read_file(self, path: str) -> str:
        data = np.fromfile(path, dtype=np.uint8)  # safe for unicode paths
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            log.warning("Cannot decode image: %s", path)
            return ""
        return self.read_array(img)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    print(ArabicOCR().read_file(sys.argv[1]))
