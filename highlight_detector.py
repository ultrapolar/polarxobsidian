"""Stage 3: Detect highlighted regions using HSV color filtering.

Detection parameters (minimum area, morphology kernels) are defined at a
reference page width in config and scaled to the actual image width at runtime,
so the same physical highlight is detected identically across scans, phone
photos, and different DPI settings.
"""

import cv2
import numpy as np

from color_profiles import HIGHLIGHT_PROFILES
from config import (
    CLOSE_KERNEL_SIZE,
    DETECT_REFERENCE_WIDTH,
    MIN_HIGHLIGHT_AREA,
    OPEN_KERNEL_SIZE,
)


def _scaled_params(image_width):
    """Scale the tuned pixel constants to this image's width."""
    s = max(0.4, image_width / DETECT_REFERENCE_WIDTH)
    min_area = MIN_HIGHLIGHT_AREA * s * s          # area scales with s²
    close_k = (max(3, round(CLOSE_KERNEL_SIZE[0] * s)),
               max(2, round(CLOSE_KERNEL_SIZE[1] * s)))
    open_k = (max(2, round(OPEN_KERNEL_SIZE[0] * s)),
              max(2, round(OPEN_KERNEL_SIZE[1] * s)))
    return min_area, close_k, open_k


def detect_highlights(image, colors):
    """Detect highlighted regions on a page image.

    Args:
        image: numpy array in RGB color order.
        colors: list of color names to detect (e.g. ["yellow", "green"]).

    Returns:
        List of dicts with keys: bbox (x, y, w, h), color (str).
        Sorted top-to-bottom, then left-to-right.
    """
    min_area, close_k, open_k = _scaled_params(image.shape[1])
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    all_highlights = []

    for color_name in colors:
        profile = HIGHLIGHT_PROFILES[color_name]
        mask = cv2.inRange(hsv, np.array(profile["lower"]),
                           np.array(profile["upper"]))

        # Close: bridge gaps along a text line; open: remove speckle noise.
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, close_k),
        )
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, open_k),
        )

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            if w * h < min_area:
                continue
            # Highlights are wider than tall; skip tall narrow blobs
            if w < h * 0.5:
                continue

            all_highlights.append({
                "bbox": (x, y, w, h),
                "color": color_name,
            })

    # Sort top-to-bottom, then left-to-right
    all_highlights.sort(key=lambda hl: (hl["bbox"][1], hl["bbox"][0]))
    return all_highlights
