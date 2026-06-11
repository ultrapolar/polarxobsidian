"""Classify a mixed folder of page photos into per-book groups.

People photograph several books into one camera roll. This module sorts the
mess: each page is identified by content, then smoothed within its shooting
session (photos taken minutes apart are almost certainly the same book).

Per-page signals, strongest first:
1. **Title match** — OCR the running-header strip (and, for covers, the page
   body) and fuzzy-match the known book titles.
2. **Reference match** — OCR a body strip and fuzzy-match it against each
   book's reference text (ebook/PDF/audiobook transcript) when provided.
3. **Session smoothing** — pages with no/weak signal take their shooting
   session's majority label; a page with strong conflicting evidence keeps
   its own label.

Blank pages and pages matching no book land in ``_unsorted``.
"""

import os
import re
from dataclasses import dataclass, field

import numpy as np

from config import (
    CLASSIFY_BODY_MIN_CHARS,
    CLASSIFY_REF_MIN_SCORE,
    CLASSIFY_REF_RUNNERUP_MARGIN,
    CLASSIFY_SESSION_GAP_MIN,
    CLASSIFY_STRONG_SCORE,
    CLASSIFY_TITLE_MIN_SCORE,
)

_TS_RE = re.compile(r"(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})")


@dataclass
class Book:
    name: str
    references: list = field(default_factory=list)   # paths
    ref_text: str = ""                               # loaded lazily


@dataclass
class PageResult:
    file: str
    session: int
    label: str          # book name, "_unsorted", or "_blank"
    method: str         # title | reference | smoothed | blank | none
    score: float


def _timestamp_minutes(filename):
    m = _TS_RE.search(filename)
    if not m:
        return None
    y, mo, d, h, mi, s = (int(g) for g in m.groups())
    # Good enough for gap detection; month length quirks don't matter here.
    return (((y * 12 + mo) * 31 + d) * 24 + h) * 60 + mi + s / 60.0


def _sessions(files, gap_minutes=CLASSIFY_SESSION_GAP_MIN):
    """Assign a session index to each file based on filename-timestamp gaps."""
    ids = []
    prev, session = None, 0
    for f in files:
        t = _timestamp_minutes(os.path.basename(f))
        if prev is not None and t is not None and (t - prev) > gap_minutes:
            session += 1
        ids.append(session)
        if t is not None:
            prev = t
    return ids


def _is_blank(image):
    """Adaptive blank check in the min-channel, relative to the paper tone.

    The min across R/G/B keeps both printed text AND highlighter ink dark (the
    max-channel would erase highlighter — wrong space for this test), and
    comparing against the page's own median brightness makes the test robust to
    exposure. Measured margins: text pages ~2.5%+ ink, blank pages ~0.1%.
    """
    dark = image.min(axis=2)
    paper = np.median(dark)
    return (dark < paper * 0.62).mean() < 0.004


def _ocr_strip(image, y0, y1):
    from image_prep import prep_for_ocr
    from ocr_engine import run_ocr

    h = image.shape[0]
    strip = image[int(h * y0):int(h * y1)]
    if strip.size == 0:
        return ""
    try:
        return run_ocr(prep_for_ocr(strip)).full_text
    except Exception:
        return ""


def _best_title(text, books):
    """(book, score) for the best fuzzy title hit inside text, or (None, 0)."""
    from rapidfuzz import fuzz

    up = text.upper()
    if len(up) < 4:
        return None, 0.0
    best, best_score = None, 0.0
    for b in books:
        score = fuzz.partial_ratio(b.name.upper(), up)
        if score > best_score:
            best, best_score = b, score
    if best_score >= CLASSIFY_TITLE_MIN_SCORE:
        return best, best_score
    return None, 0.0


def _best_reference(text, books):
    """(book, score) for the best reference-text hit, or (None, 0)."""
    from rapidfuzz import fuzz

    low = " ".join(text.lower().split())[:400]
    if len(low) < CLASSIFY_BODY_MIN_CHARS:
        return None, 0.0
    scored = []
    for b in books:
        if b.ref_text:
            scored.append((fuzz.partial_ratio(low, b.ref_text), b))
    if not scored:
        return None, 0.0
    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top = scored[0]
    runner = scored[1][0] if len(scored) > 1 else 0.0
    if top_score >= CLASSIFY_REF_MIN_SCORE and \
            top_score - runner >= CLASSIFY_REF_RUNNERUP_MARGIN:
        return top, top_score
    return None, 0.0


def classify_pages(folder, books, log=print):
    """Classify every image in folder. Returns a list of PageResult in order."""
    from pdf_converter import _image_files_in, _load_image_file
    from reference_matcher import load_reference_text

    for b in books:
        texts = []
        for ref in b.references:
            try:
                texts.append(load_reference_text(ref, log=log))
            except Exception as e:
                log(f"  ! reference for '{b.name}' failed to load: {e}")
        b.ref_text = " ".join(t.lower() for t in texts if t)

    files = _image_files_in(folder)
    if not files:
        raise FileNotFoundError(f"No images found in {folder}")
    session_ids = _sessions(files)

    log(f"Classifying {len(files)} pages across {session_ids[-1] + 1} session(s) ...")
    results = []
    for i, f in enumerate(files):
        name = os.path.basename(f)
        try:
            image = _load_image_file(f)
        except Exception:
            results.append(PageResult(f, session_ids[i], "_unsorted", "none", 0.0))
            continue

        if _is_blank(image):
            results.append(PageResult(f, session_ids[i], "_blank", "blank", 0.0))
            continue

        header = _ocr_strip(image, 0.0, 0.18)
        book, score = _best_title(header, books)
        method = "title"
        if book is None:
            body = _ocr_strip(image, 0.20, 0.75)
            book, score = _best_title(body, books)   # covers carry the title mid-page
            if book is None:
                book, score = _best_reference(body, books)
                method = "reference"
        if book is None:
            results.append(PageResult(f, session_ids[i], "_unknown", "none", 0.0))
        else:
            results.append(PageResult(f, session_ids[i], book.name, method, score))

        if (i + 1) % 50 == 0:
            log(f"  ... {i + 1}/{len(files)}")

    _smooth_sessions(results, log)
    return results


def _smooth_sessions(results, log):
    """Fill weak/unknown pages with their session's majority label."""
    from collections import Counter

    by_session = {}
    for r in results:
        by_session.setdefault(r.session, []).append(r)

    for sid, pages in by_session.items():
        votes = Counter(
            r.label for r in pages
            if r.label not in ("_unknown", "_blank", "_unsorted")
        )
        if not votes:
            for r in pages:
                if r.label == "_unknown":
                    r.label = "_unsorted"
            continue
        majority, _count = votes.most_common(1)[0]
        for r in pages:
            if r.label == "_unknown":
                r.label, r.method = majority, "smoothed"
            elif r.label == "_blank":
                # keep blanks with the book so page order stays contiguous
                r.label, r.method = majority, "blank"
            elif r.label != majority and r.score < CLASSIFY_STRONG_SCORE:
                # weak minority evidence inside a homogeneous session
                r.label, r.method = majority, "smoothed"
        log(f"  session {sid}: {len(pages)} page(s) -> {majority}")


def sort_into_folders(results, out_root, log=print):
    """Copy classified pages into per-book folders. Returns {label: folder}."""
    import shutil

    def safe(name):
        return re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "_unsorted"

    folders = {}
    for r in results:
        label = r.label if not r.label.startswith("_") else "_unsorted"
        dest = folders.get(label)
        if dest is None:
            dest = os.path.join(out_root, safe(label))
            os.makedirs(dest, exist_ok=True)
            folders[label] = dest
        shutil.copy2(r.file, os.path.join(dest, os.path.basename(r.file)))

    for label, dest in sorted(folders.items()):
        n = sum(1 for r in results
                if (r.label if not r.label.startswith("_") else "_unsorted") == label)
        log(f"  {label}: {n} page(s) -> {dest}")
    return folders
