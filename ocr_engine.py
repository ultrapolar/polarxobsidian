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


def run_ocr(image):
    """Run Tesseract OCR on a page image.

    Returns an OCRResult with the full page text and a list of OCRWord
    objects, each containing text and its bounding box on the page.
    """
    psm_config = f"--psm {TESSERACT_PSM}"

    # Word-level bounding boxes
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

    # Full text in reading order
    full_text = pytesseract.image_to_string(image, config=psm_config)

    return OCRResult(full_text=full_text, words=words)
