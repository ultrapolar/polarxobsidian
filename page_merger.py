"""Merge a highlight split across a page break into one entry.

A quote that runs off the bottom of one page and continues at the top of the
next is detected as two separate passages (each page is processed alone). This
pass stitches such a pair together. It is deliberately multi-signal, because the
single geometric test is unreliable on phone photos (where the page doesn't fill
the frame). For consecutive pages, the earlier passage's last word(s) and the
later passage's first word(s) are checked against, strongest first:

1. **Reference bridge** — if a clean reference is available and "prev tail +
   cur head" appears contiguously in it, they are the same quote. Definitive and
   independent of how the page was framed. (And if *both* halves matched the
   reference but do NOT bridge, they are genuinely separate — don't merge.)
2. **Cut sentence** — the earlier highlight ends mid-sentence (no terminal
   punctuation), i.e. the page break sliced a sentence in two.
3. **Geometry** — the earlier highlight ends in the page's bottom edge band and
   the later one starts in the top band (best for clean scans).
"""

from config import (
    CROSS_PAGE_BRIDGE_MIN_SCORE,
    CROSS_PAGE_BRIDGE_WORDS,
    PAGE_EDGE_RATIO,
)
from text_utils import smart_join

_SENTENCE_END = ".!?"
_TRAILING = "\"')]}>»”’ "


def _ends_at_bottom(entry):
    h = entry.get("end_page_height") or 0
    return h > 0 and entry["end_y"] >= h * (1 - PAGE_EDGE_RATIO)


def _starts_at_top(entry):
    h = entry.get("start_page_height") or 0
    return h > 0 and entry["start_y"] <= h * PAGE_EDGE_RATIO


def _ends_midsentence(text):
    t = (text or "").rstrip(_TRAILING)
    return bool(t) and t[-1] not in _SENTENCE_END


def _bridges_in_reference(prev_text, cur_text, ref_texts):
    """True if prev's tail + cur's head appear contiguously in any reference."""
    if not ref_texts:
        return False
    tail = " ".join(prev_text.split()[-CROSS_PAGE_BRIDGE_WORDS:])
    head = " ".join(cur_text.split()[:CROSS_PAGE_BRIDGE_WORDS])
    bridge = f"{tail} {head}".strip().lower()
    if len(bridge.split()) < 4:
        return False
    from rapidfuzz import fuzz
    return any(
        rt and fuzz.partial_ratio(bridge, rt.lower()) >= CROSS_PAGE_BRIDGE_MIN_SCORE
        for rt in ref_texts
    )


def _should_merge(prev, cur, ref_texts):
    if cur["page"] != prev["page"] + 1:
        return False

    if _bridges_in_reference(prev["highlight_text"], cur["highlight_text"], ref_texts):
        return True
    # Both halves matched the reference but didn't bridge -> genuinely separate.
    if ref_texts and prev.get("matched") and cur.get("matched"):
        return False

    if _ends_midsentence(prev["highlight_text"]):
        return True
    return _ends_at_bottom(prev) and _starts_at_top(cur)


def merge_cross_page(results, ref_texts=None):
    """Return a new results list with page-spanning highlights merged.

    ``ref_texts`` is an optional list of reference texts used to confirm that two
    fragments really are contiguous in the book.
    """
    merged = []
    for cur in results:
        if merged and _should_merge(merged[-1], cur, ref_texts):
            prev = merged[-1]
            prev.update({
                "highlight_text": smart_join(prev["highlight_text"], cur["highlight_text"]),
                "after": cur["after"],           # trailing context from the later half
                "color": ", ".join(dict.fromkeys(
                    c for c in (prev["color"] + ", " + cur["color"]).split(", ") if c
                )),
                "mark_phrases": prev.get("mark_phrases", []) + cur.get("mark_phrases", []),
                "end_y": cur["end_y"],
                "end_page_height": cur.get("end_page_height"),
                "spans_pages": (prev.get("spans_pages", (prev["page"],))[0], cur["page"]),
                # Confidence inputs: take the weaker half (conservative).
                "ocr_conf": min(prev.get("ocr_conf", 0), cur.get("ocr_conf", 0)),
                "match_score": min(prev.get("match_score", 0), cur.get("match_score", 0)),
                "match_fraction": min(prev.get("match_fraction", 0), cur.get("match_fraction", 0)),
                "matched": prev.get("matched") or cur.get("matched"),
            })
            continue
        merged.append(dict(cur))

    return merged
