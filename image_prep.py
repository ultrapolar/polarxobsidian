"""Pre-process page images so highlighter colour doesn't degrade OCR.

Highlighters are light and coloured; printed text is dark in *every* colour
channel. Taking the per-pixel maximum across R/G/B turns any light highlighter
(orange, yellow, pink, green, blue) to near-white while leaving dark text dark —
so text under a highlight OCRs as cleanly as the rest of the page.

Highlight *detection* still runs on the original colour image; only the OCR copy
is pre-processed (both share the same pixel coordinates).
"""

import cv2
import numpy as np

from config import OCR_PREP_ENABLED


def prep_for_ocr(image):
    """Return a grayscale image with light coloured highlighter neutralised."""
    if not OCR_PREP_ENABLED:
        return image

    # Max across channels: light colour -> white, dark text stays dark.
    gray = image.max(axis=2).astype(np.uint8)

    # Light denoise + CLAHE so faint text stays legible under uneven lighting.
    gray = cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7,
                                    searchWindowSize=21)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)
