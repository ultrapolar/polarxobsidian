# HSV color range definitions for highlight detection.
# HSV ranges: H (0-179), S (0-255), V (0-255) in OpenCV.
# Ranges are tuned to distinguish fluorescent highlighter marks from
# aged/yellowed paper (which typically has S < 40).

HIGHLIGHT_PROFILES = {
    "yellow": {
        "lower": (15, 60, 180),
        "upper": (40, 255, 255),
    },
    "green": {
        "lower": (35, 60, 150),
        "upper": (85, 255, 255),
    },
    "pink": {
        "lower": (140, 40, 180),
        "upper": (175, 255, 255),
    },
    "blue": {
        "lower": (85, 50, 150),
        "upper": (135, 255, 255),
    },
    "orange": {
        "lower": (5, 80, 180),
        "upper": (18, 255, 255),
    },
}

ALL_COLORS = list(HIGHLIGHT_PROFILES.keys())
