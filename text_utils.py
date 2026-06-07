"""Small text helpers shared across the pipeline."""

import os
import re


def writable_path(path):
    """Return ``path``, or a numbered variant if it's locked (e.g. open in Excel).

    Prevents a held-open output file from crashing a long run — the result is
    just written next to it as "name (1).ext".
    """
    base, ext = os.path.splitext(path)
    candidate, n = path, 1
    while n <= 50:
        try:
            with open(candidate, "a", encoding="utf-8"):
                return candidate
        except (PermissionError, OSError):
            candidate = f"{base} ({n}){ext}"
            n += 1
    return path


def _norm(word):
    """Normalize a word for overlap comparison (drop punctuation, lowercase)."""
    return re.sub(r"[^\w]", "", word).lower()


def smart_join(a, b, max_overlap=6):
    """Join two text fragments, trimming a duplicated word run at the seam.

    Sentence-level reference matching (and cross-page merging) can repeat words
    at a boundary — e.g. correcting "They're both me." then a next fragment that
    matched "Both me, that college dropout…" yields "…both me. both me. that…".
    This collapses the largest overlap (up to ``max_overlap`` words) between the
    tail of ``a`` and the head of ``b``.
    """
    a = a.strip()
    b = b.strip()
    if not a:
        return b
    if not b:
        return a

    aw, bw = a.split(), b.split()
    an = [_norm(w) for w in aw]
    bn = [_norm(w) for w in bw]

    overlap = 0
    for k in range(min(max_overlap, len(aw), len(bw)), 0, -1):
        if an[-k:] == bn[:k]:
            overlap = k
            break

    return " ".join(aw + bw[overlap:])


def locate_phrases(text, phrases, min_score=75):
    """Find each (phrase, colour) inside text; return merged (start, end, colour).

    Exact substring first, then a fuzzy fallback (so an OCR phrase like
    "che slight edge" still locates inside a clean "the slight edge").
    """
    if not phrases:
        return []
    low = text.lower()
    spans = []
    for phrase, colour in phrases:
        p = phrase.strip()
        if not p:
            continue
        idx = low.find(p.lower())
        if idx >= 0:
            spans.append((idx, idx + len(p), colour))
            continue
        from rapidfuzz import fuzz
        al = fuzz.partial_ratio_alignment(p.lower(), low, score_cutoff=min_score)
        if al and al.dest_end > al.dest_start:
            spans.append((al.dest_start, al.dest_end, colour))

    # Snap each span out to whole-word boundaries (fuzzy alignment can clip a
    # character, e.g. marking "hy" instead of "Why").
    snapped = []
    for s, e, c in spans:
        while s > 0 and (text[s - 1].isalnum() or text[s - 1] in "’'"):
            s -= 1
        while e < len(text) and (text[e].isalnum() or text[e] in "’'"):
            e += 1
        snapped.append((s, e, c))
    spans = snapped

    spans.sort()
    merged = []
    for s, e, c in spans:
        if merged and s <= merged[-1][1]:
            ps, pe, pc = merged[-1]
            merged[-1] = (ps, max(pe, e), pc)
        else:
            merged.append((s, e, c))
    return merged


def mark_html(text, phrases, color_map, default):
    """Wrap each located phrase in a coloured <mark> tag."""
    spans = locate_phrases(text, phrases)
    out, pos = [], 0
    for s, e, c in spans:
        out.append(text[pos:s])
        out.append(f'<mark style="background: {color_map.get(c, default)};">'
                   f'{text[s:e]}</mark>')
        pos = e
    out.append(text[pos:])
    return "".join(out)


def bold_parts(text, phrases):
    """Return [(segment, is_bold)] with the located phrases marked bold."""
    spans = locate_phrases(text, phrases)
    parts, pos = [], 0
    for s, e, _c in spans:
        if s > pos:
            parts.append((text[pos:s], False))
        parts.append((text[s:e], True))
        pos = e
    if pos < len(text):
        parts.append((text[pos:], False))
    return parts or [(text, False)]
