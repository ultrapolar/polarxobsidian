"""Stage 4: Match highlight bounding boxes to OCR words and extract context."""

import re

from config import (
    MAX_PASSAGE_GAP,
    MIN_PASSAGE_WORDS,
    WORD_OVERLAP_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Word-to-highlight overlap
# ---------------------------------------------------------------------------

def _overlap_ratio(word_box, hl_box):
    """Fraction of the word's width that falls inside the highlight box."""
    wx, wy, ww, wh = word_box
    hx, hy, hw, hh = hl_box

    # Vertical overlap check
    vert_overlap = min(wy + wh, hy + hh) - max(wy, hy)
    if vert_overlap < wh * 0.3:
        return 0.0

    # Horizontal overlap
    horiz_overlap = min(wx + ww, hx + hw) - max(wx, hx)
    if horiz_overlap <= 0:
        return 0.0

    return horiz_overlap / ww


def match_highlight_to_words(hl_bbox, ocr_words, threshold=WORD_OVERLAP_THRESHOLD):
    """Find OCR words that overlap a highlight bounding box.

    Returns list of OCRWord objects in reading order.
    """
    matched = []
    for w in ocr_words:
        word_box = (w.x, w.y, w.w, w.h)
        if _overlap_ratio(word_box, hl_bbox) >= threshold:
            matched.append(w)

    matched.sort(key=lambda w: (w.block, w.par, w.line, w.word_idx))
    return matched


def _reading_order(words):
    """Return OCR words sorted into reading order."""
    return sorted(words, key=lambda w: (w.block, w.par, w.line, w.word_idx))


# Stable color ordering for passages that span more than one highlighter color.
_COLOR_ORDER = ["yellow", "green", "pink", "blue", "orange"]


def _sentence_ranges(ordered):
    """Split the page's words into sentences as inclusive (start, end) index ranges."""
    ranges = []
    start = 0
    for i, w in enumerate(ordered):
        if re.search(r"[.!?][\"')\]”’]*$", w.text):
            ranges.append((start, i))
            start = i + 1
    if start < len(ordered):
        ranges.append((start, len(ordered) - 1))
    return ranges


def _join(words):
    return " ".join(w.text for w in words).strip()


def extract_highlight_passages(highlights, ocr_words, max_gap=MAX_PASSAGE_GAP,
                               min_words=MIN_PASSAGE_WORDS):
    """Turn highlight regions into sentence-aware, context-rich passages.

    Because people highlight specific *words* (not whole quotes), each passage is
    built around whole sentences for readability:

    1. Mark every word overlapping a highlight region (with its colour).
    2. Take the sentence(s) that contain highlighted words. Consecutive
       highlighted sentences (and multiple highlights within one sentence) are
       merged into a single passage; a fully-unhighlighted sentence ends it.
    3. ``text`` = those highlighted sentence(s); ``before``/``after`` = the one
       sentence on each side (context). ``mark_phrases`` lists the exact
       highlighted word-runs (gap-filled) so the actual words can still be
       marked within the sentences.

    Returns dicts: ``text``, ``before``, ``after``, ``color``, ``mark_phrases``
    (list of ``(phrase, colour_name)``), ``start_y``, ``end_y``.
    """
    ordered = _reading_order(ocr_words)
    pos_by_key = {
        (w.block, w.par, w.line, w.word_idx): i for i, w in enumerate(ordered)
    }

    colors_at = {}
    for hl in highlights:
        for w in match_highlight_to_words(hl["bbox"], ocr_words):
            pos = pos_by_key.get((w.block, w.par, w.line, w.word_idx))
            if pos is not None:
                colors_at.setdefault(pos, set()).add(hl["color"])
    if not colors_at:
        return []

    sentences = _sentence_ranges(ordered)
    sent_of = {}
    for si, (a, b) in enumerate(sentences):
        for p in range(a, b + 1):
            sent_of[p] = si

    # Highlighted sentence index -> colours present in it.
    hl_sent_colors = {}
    for p, cols in colors_at.items():
        si = sent_of.get(p)
        if si is not None:
            hl_sent_colors.setdefault(si, set()).update(cols)

    # Group consecutive highlighted sentence indices (gap of 0 = one passage).
    groups = []
    for si in sorted(hl_sent_colors):
        if groups and si <= groups[-1][1] + 1:
            groups[-1][1] = si
            groups[-1][2] |= hl_sent_colors[si]
        else:
            groups.append([si, si, set(hl_sent_colors[si])])

    passages = []
    for s_first, s_last, cols in groups:
        hw_start, hw_end = sentences[s_first][0], sentences[s_last][1]

        # Highlighted word-runs within the group's sentences -> mark phrases.
        hl_positions = [p for p in sorted(colors_at) if hw_start <= p <= hw_end]
        runs = [[hl_positions[0]]]
        for p in hl_positions[1:]:
            if p - runs[-1][-1] <= max_gap:
                runs[-1].append(p)
            else:
                runs.append([p])

        total_hl_words = sum(len(r) for r in runs)
        if total_hl_words < min_words and len(runs) == 1 and \
                len(ordered[runs[0][0]].text) < 3:
            continue  # drop a lone tiny mark (likely noise)

        mark_phrases = []
        for run in runs:
            phrase = _join(ordered[run[0]:run[-1] + 1])
            run_cols = set().union(*(colors_at[p] for p in run))
            colour = next((c for c in _COLOR_ORDER if c in run_cols), "yellow")
            if phrase:
                mark_phrases.append((phrase, colour))

        text = _join(ordered[hw_start:hw_end + 1])
        if not text:
            continue

        before = _join(ordered[sentences[s_first - 1][0]:sentences[s_first - 1][1] + 1]) \
            if s_first > 0 else ""
        after = _join(ordered[sentences[s_last + 1][0]:sentences[s_last + 1][1] + 1]) \
            if s_last < len(sentences) - 1 else ""

        color = ", ".join(c for c in _COLOR_ORDER if c in cols)

        passages.append({
            "text": text,
            "before": before,
            "after": after,
            "color": color,
            "mark_phrases": mark_phrases,
            "start_y": ordered[hw_start].y,
            "end_y": ordered[hw_end].y + ordered[hw_end].h,
        })

    return passages
