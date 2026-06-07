"""Stage 3: Detect highlighted regions using HSV color filtering."""

import cv2
import numpy as np

from color_profiles import HIGHLIGHT_PROFILES
from config import CLOSE_KERNEL_SIZE, MIN_HIGHLIGHT_AREA, OPEN_KERNEL_SIZE


def detect_highlights(image, colors):
    """Detect highlighted regions on a page image.

    Args:
        image: numpy array in RGB color order.
        colors: list of color names to detect (e.g. ["yellow", "green"]).

    Returns:
        List of dicts with keys: bbox (x, y, w, h), color (str).
        Sorted top-to-bottom, then left-to-right.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    all_highlights = []

    for color_name in colors:
        profile = HIGHLIGHT_PROFILES[color_name]
        lower = np.array(profile["lower"])
        upper = np.array(profile["upper"])

        mask = cv2.inRange(hsv, lower, upper)

        # Morphological close: bridge gaps along a text line
        horiz_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, CLOSE_KERNEL_SIZE
        )
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, horiz_kernel)

        # Morphological open: remove small noise
        small_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, OPEN_KERNEL_SIZE
        )
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, small_kernel)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            area = w * h
            if area < MIN_HIGHLIGHT_AREA:
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
