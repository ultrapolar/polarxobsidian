"""Stage 2: Full-page OCR with word-level bounding boxes."""

import glob
import os
import shutil
from dataclasses import dataclass, field

import pytesseract

from config import OCR_CONFIDENCE_THRESHOLD, TESSERACT_PSM


def _locate_tesseract():
    """Point pytesseract at tesseract.exe if it isn't already on PATH.

    The UB-Mannheim Windows installer does not add Tesseract to PATH, so check
    the usual install locations and configure pytesseract directly.
    """
    if shutil.which("tesseract"):
        return  # already on PATH

    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    candidates += glob.glob(os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*Tesseract*\tesseract.exe"
    ))
    for path in candidates:
        if os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return


_locate_tesseract()


@dataclass
class OCRWord:
    text: str
    x: int
    y: int
    w: int
    h: int
    conf: int
    block: int
    par: int
    line: int
    word_idx: int


@dataclass
class OCRResult:
    full_text: str
    words: list = field(default_factory=list)
    mean_conf: float = 0.0      # mean word confidence (0-100), quality signal


def run_ocr(image, psm=None):
    """Run Tesseract OCR on a page image.

    Returns an OCRResult with the page text (derived from the word list — a
    single Tesseract pass), word boxes, and the mean word confidence.
    """
    psm_config = f"--psm {psm if psm is not None else TESSERACT_PSM}"

    data = pytesseract.image_to_data(
        image, output_type=pytesseract.Output.DICT, config=psm_config
    )

    words = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = int(data["conf"][i])
        if text and conf > OCR_CONFIDENCE_THRESHOLD:
            words.append(
                OCRWord(
                    text=text,
                    x=data["left"][i],
                    y=data["top"][i],
                    w=data["width"][i],
                    h=data["height"][i],
                    conf=conf,
                    block=data["block_num"][i],
                    par=data["par_num"][i],
                    line=data["line_num"][i],
                    word_idx=data["word_num"][i],
                )
            )

    full_text = " ".join(w.text for w in words)
    mean_conf = round(sum(w.conf for w in words) / len(words), 1) if words else 0.0
    return OCRResult(full_text=full_text, words=words, mean_conf=mean_conf)


def run_ocr_best(image, prepped):
    """Accuracy-first OCR: try variants, keep the one with the best confidence.

    The prepped (highlighter-neutralised) image is the primary. If its mean word
    confidence is already high we stop there; otherwise we also try the original
    colour image, auto page segmentation (PSM 3), and an upscaled render, and
    keep whichever reads best. Word boxes are always mapped back to the original
    image's coordinates so highlight overlap still works.

    Returns (best OCRResult, variant_name).
    """
    from config import OCR_RETRY_MIN_CONF, OCR_UPSCALE

    best = run_ocr(prepped)
    if best.mean_conf >= OCR_RETRY_MIN_CONF:
        return best, "prepped"

    candidates = [("prepped", best)]

    try:
        candidates.append(("original", run_ocr(image)))
    except Exception:
        pass
    try:
        candidates.append(("prepped-psm3", run_ocr(prepped, psm=3)))
    except Exception:
        pass
    try:
        import cv2
        h, w = prepped.shape[:2]
        big = cv2.resize(prepped, (int(w * OCR_UPSCALE), int(h * OCR_UPSCALE)),
                         interpolation=cv2.INTER_CUBIC)
        up = run_ocr(big)
        for word in up.words:   # map boxes back to original coordinates
            word.x = int(word.x / OCR_UPSCALE)
            word.y = int(word.y / OCR_UPSCALE)
            word.w = max(1, int(word.w / OCR_UPSCALE))
            word.h = max(1, int(word.h / OCR_UPSCALE))
        candidates.append(("upscaled", up))
    except Exception:
        pass

    name, result = max(candidates, key=lambda c: c[1].mean_conf)
    return result, name
