"""Correct OCR'd highlight text by aligning it to a clean reference book.

OCR on scanned pages produces real-word errors (``chat``->``that``, ``che``->
``the``) that spell-checkers cannot catch. If the user supplies a digital copy
of the book (.epub or .txt), we fuzzy-align each highlighted passage to the
reference text and replace the OCR output with the original wording.

Matching uses ``rapidfuzz.fuzz.partial_ratio_alignment`` with a moving cursor:
because highlights are produced in reading order, we search a window of the
reference just ahead of the previous match. This is both fast (no full-book
scan per passage) and more accurate (a common phrase won't match the wrong
chapter).
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from config import (
    REFERENCE_LEN_MAX_RATIO,
    REFERENCE_LEN_MIN_RATIO,
    REFERENCE_MIN_OCR_CHARS,
    REFERENCE_MIN_SCORE,
    REFERENCE_REANCHOR_SCORE,
    REFERENCE_SEARCH_WINDOW,
    REFERENCE_WINDOW_LOOKBACK,
)


# ---------------------------------------------------------------------------
# Loading reference text
# ---------------------------------------------------------------------------

def _normalize_ws(text):
    """Collapse all runs of whitespace to single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def _strip_html(html):
    """Best-effort HTML -> text (BeautifulSoup if present, else a regex strip)."""
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text(" ")
    except ImportError:
        return re.sub(r"<[^>]+>", " ", html)


def _load_zip_xml(path, member_glob):
    """Pull text from XML/HTML members of a zip (epub/docx fallback)."""
    import fnmatch
    import zipfile

    chunks = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if fnmatch.fnmatch(name.lower(), member_glob):
                chunks.append(_strip_html(z.read(name).decode("utf-8", "ignore")))
    return " ".join(chunks)


def _load_epub(path):
    # Primary: ebooklib; fallback: read the zip's XHTML directly.
    try:
        import ebooklib
        from ebooklib import epub
        book = epub.read_epub(path)
        chunks = [_strip_html(item.get_content().decode("utf-8", "ignore"))
                  for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)]
        text = _normalize_ws(" ".join(chunks))
        if text:
            return text
    except Exception:
        pass
    return _normalize_ws(_load_zip_xml(path, "*.*html"))


def _load_pdf(path):
    """Extract text from a digital (text-based) PDF. Tries pypdf, then Poppler's
    ``pdftotext``. A different edition is fine — fuzzy matching is tolerant."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        text = _normalize_ws(" ".join((p.extract_text() or "") for p in reader.pages))
        if text:
            return text
    except Exception:
        pass
    # Fallback: pdftotext (Poppler) if available.
    import shutil
    import subprocess
    if shutil.which("pdftotext"):
        try:
            out = subprocess.run(["pdftotext", "-q", path, "-"],
                                 capture_output=True, text=True, timeout=300)
            return _normalize_ws(out.stdout)
        except Exception:
            pass
    return ""


def _load_docx(path):
    return _normalize_ws(_load_zip_xml(path, "word/document*.xml"))


def _load_txt(path):
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                return _normalize_ws(f.read())
        except (UnicodeDecodeError, OSError):
            continue
    with open(path, encoding="utf-8", errors="ignore") as f:
        return _normalize_ws(f.read())


def load_reference_text(path, log=print):
    """Load reference text from a source (whitespace-normalized).

    Supported: ``.epub``, ``.pdf`` (text-based), ``.docx``, ``.txt``, and audio
    (a file or folder of audio, which is transcribed). Each loader has a fallback
    so a missing library or odd file degrades gracefully instead of aborting.
    """
    import audio_transcriber

    lower = path.lower()
    if lower.endswith(".epub"):
        return _load_epub(path)
    if lower.endswith(".pdf"):
        return _load_pdf(path)
    if lower.endswith((".docx", ".doc")):
        return _load_docx(path)
    if audio_transcriber.is_audio(path):
        return _normalize_ws(audio_transcriber.transcribe(path, log=log))
    return _load_txt(path)


# ---------------------------------------------------------------------------
# Correction
# ---------------------------------------------------------------------------

@dataclass
class Correction:
    text: str           # corrected (or original) passage text
    score: float        # match confidence 0-100
    span: tuple         # (start, end) char offsets in the reference, or None
    matched: bool       # True if a confident reference match was found


class ReferenceCorrector:
    """Aligns OCR passages to a reference text, in reading order."""

    def __init__(self, reference_text, min_score=REFERENCE_MIN_SCORE,
                 reanchor_score=REFERENCE_REANCHOR_SCORE,
                 window=REFERENCE_SEARCH_WINDOW,
                 lookback=REFERENCE_WINDOW_LOOKBACK):
        self.ref = reference_text
        self.ref_lower = reference_text.lower()
        self.min_score = min_score
        self.reanchor_score = reanchor_score
        self.window = window
        self.lookback = lookback
        self.cursor = 0

    def _expand_to_words(self, start, end):
        """Grow [start, end) outward so it doesn't cut words mid-token."""
        while start > 0 and not self.ref[start - 1].isspace():
            start -= 1
        n = len(self.ref)
        while end < n and not self.ref[end].isspace():
            end += 1
        return start, end

    def _align(self, ocr_lower, hay_lower, offset, cutoff):
        """Return (score, global_start, global_end) or None for one search."""
        al = fuzz.partial_ratio_alignment(ocr_lower, hay_lower, score_cutoff=cutoff)
        if al is None:
            return None
        return al.score, offset + al.dest_start, offset + al.dest_end

    def _length_ok(self, ocr_len, gs, ge):
        """Guard against spurious matches whose span length is wildly off."""
        span_len = ge - gs
        if ocr_len == 0:
            return False
        ratio = span_len / ocr_len
        return REFERENCE_LEN_MIN_RATIO <= ratio <= REFERENCE_LEN_MAX_RATIO

    def correct(self, ocr_text):
        """Correct one passage. Advances the cursor on a confident match.

        Two-tier matching: a LOCAL match within the in-order window just ahead of
        the cursor is accepted at a lower bar (we've already anchored to the right
        region); a global RE-ANCHOR is held to a stricter bar so we don't jump to
        a spurious match elsewhere in the book.
        """
        ocr_lower = ocr_text.lower().strip()
        # Short fragments match spuriously (and can mis-anchor the cursor), so
        # leave them to the spell-check fallback.
        if len(ocr_lower) < REFERENCE_MIN_OCR_CHARS:
            return Correction(ocr_text, 0.0, None, False)

        # 1) Search a window just ahead of the last match (fast, order-aware).
        win_start = max(0, self.cursor - self.lookback)
        win_end = min(len(self.ref), win_start + self.window)
        hit = self._align(
            ocr_lower, self.ref_lower[win_start:win_end], win_start, self.min_score
        )

        # 2) Fall back to a stricter full-book search to re-anchor if needed.
        if hit is None:
            hit = self._align(ocr_lower, self.ref_lower, 0, self.reanchor_score)

        if hit is None:
            return Correction(ocr_text, 0.0, None, False)

        score, gs, ge = hit
        gs, ge = self._expand_to_words(gs, ge)
        if not self._length_ok(len(ocr_lower), gs, ge):
            return Correction(ocr_text, score, None, False)

        self.cursor = ge
        return Correction(self.ref[gs:ge].strip(), score, (gs, ge), True)


class MultiReferenceCorrector:
    """Correct passages against one or more reference sources, combined.

    Each highlighted passage is split into sentences. Every sentence is matched
    against *every* reference and the highest-scoring confident match wins — so
    one source (e.g. the audiobook) can fix sentences another source's edition
    reworded, and vice versa. Sentences that match nowhere fall back to a
    conservative spell-check.
    """

    def __init__(self, correctors):
        self.correctors = list(correctors)

    def correct_passage(self, ocr_text):
        sentences = re.split(r"(?<=[.!?])\s+", ocr_text.strip())
        sentences = [s for s in sentences if s.strip()]
        if not sentences:
            return Correction(ocr_text, 0.0, None, False)

        from spell_corrector import spell_fix
        from text_utils import smart_join

        text = ""
        matched_any = False
        for sent in sentences:
            best = None
            for corrector in self.correctors:
                c = corrector.correct(sent)
                if c.matched and (best is None or c.score > best.score):
                    best = c
            if best is not None:
                piece = best.text
                matched_any = True
            else:
                # Not in any reference (or different wording): spell-check it.
                piece = spell_fix(sent)
            # Join trimming any duplicated words at the seam (sentence-level
            # matches can repeat a phrase across a boundary).
            text = smart_join(text, piece)

        return Correction(text.strip(), 100.0 if matched_any else 0.0,
                          None, matched_any)
