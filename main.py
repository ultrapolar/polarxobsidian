"""PDF Highlight Extractor — extract highlighted text from scanned book pages."""

import argparse
import os
import sys

from color_profiles import ALL_COLORS
from config import DEFAULT_DPI
from csv_exporter import export_to_csv
from excel_exporter import export_to_excel
from highlight_detector import detect_highlights
from ocr_engine import run_ocr_best
from page_merger import merge_cross_page
from spell_corrector import spell_fix
from text_matcher import extract_highlight_passages


def _build_parts(before, highlight, after, mark_phrases):
    """Build [(text, is_bold)] for the exporters: the highlight in its sentence
    context, with the actual highlighted words bold. Seams are de-duplicated."""
    from text_utils import bold_parts, smart_join

    full = smart_join(smart_join(before, highlight), after)
    return bold_parts(full, mark_phrases)


def _classify_source(path):
    """Classify a reference path into an archive-priority kind."""
    import audio_transcriber

    low = path.lower()
    if low.endswith(".epub"):
        return "epub"
    if low.endswith(".pdf"):
        return "pdf"
    if low.endswith((".doc", ".docx")):
        return "doc"
    if audio_transcriber.is_audio(path):
        return "audio"
    return "txt"


def _pick_archive_source(sources):
    """Choose the archive full-text by priority: epub > audio > pdf > txt/doc.

    Only sources that actually loaded text are eligible.
    """
    from config import ARCHIVE_SOURCE_PRIORITY

    by_kind = {}
    for s in sources:
        if s.get("text"):
            by_kind.setdefault(s["kind"], s)
    for kind in ARCHIVE_SOURCE_PRIORITY:
        if kind in by_kind:
            return by_kind[kind]
    return next((s for s in sources if s.get("text")), None)


def _load_sources(references, log):
    """Load each reference, resilient to a failed/empty one (logged, skipped).

    Returns a list of source dicts: kind, path, text, chars, status, and (for
    audio) a transcription metadata block.
    """
    import audio_transcriber
    from reference_matcher import load_reference_text

    sources = []
    for ref in references or []:
        kind = _classify_source(ref)
        name = os.path.basename(ref.rstrip(os.sep)) or ref
        log(f"Loading reference: {name} ...")
        try:
            text = load_reference_text(ref, log=log)
        except Exception as e:  # one bad source must not abort the run
            log(f"  ! failed to load reference {name}: {e} — skipping.")
            sources.append({"kind": kind, "path": ref, "text": "", "chars": 0,
                            "status": f"failed: {e}"})
            continue
        if not (text or "").strip():
            log(f"  ! reference {name} produced no usable text — skipping.")
            sources.append({"kind": kind, "path": ref, "text": "", "chars": 0,
                            "status": "empty"})
            continue
        src = {"kind": kind, "path": ref, "text": text, "chars": len(text),
               "status": "loaded"}
        if kind == "audio":
            meta = audio_transcriber.transcription_meta(ref)
            if meta:
                src["transcription"] = meta
        sources.append(src)
    return sources


def _correct_text(results, sources, log):
    """In place: fix OCR text via reference matching, then spell-check fallback.

    All loaded sources are combined: each sentence is matched against every
    source and the best confident hit wins.
    """
    from reference_matcher import MultiReferenceCorrector, ReferenceCorrector

    correctors = [ReferenceCorrector(s["text"]) for s in sources if s.get("text")]
    multi = MultiReferenceCorrector(correctors) if correctors else None

    from grammar_corrector import grammar_fix

    matched = 0
    for r in results:
        if multi is not None:
            c = multi.correct_passage(r["highlight_text"])
            r["highlight_text"] = c.text
            r["match_score"] = c.score
            r["match_fraction"] = c.fraction
            if c.matched:
                r["matched"] = True
                matched += 1
        else:
            r["highlight_text"] = grammar_fix(spell_fix(r["highlight_text"]))
            r["match_score"] = 0.0
            r["match_fraction"] = 0.0
        # Context sentences get the cheap layers only — reference-correcting
        # them separately makes the matcher over-reach at sentence boundaries.
        r["before"] = grammar_fix(spell_fix(r["before"]))
        r["after"] = grammar_fix(spell_fix(r["after"]))

    if multi is not None:
        log(f"  Reference-matched {matched}/{len(results)} passages "
            f"(combined {len(correctors)} source(s); spell-checked the rest).")
    else:
        log(f"  Spell-checked {len(results)} passages (no reference provided).")


def process_pdf(input_path, output_path, colors=None, dpi=DEFAULT_DPI,
                title="", author="", references=None, log=print):
    """Run the full extraction pipeline on a PDF, image, or folder of images.

    1. Load + OCR + detect highlights per page (single streaming pass).
    2. Assemble sentence-aware passages.
    3. Correct text (reference-match the combined sources, then spell-check).
    4. Merge highlights split across a page break.
    5. Export Readwise CSV, Excel, Obsidian notes, and an analytics JSON.

    ``output_path`` is a base name. ``references`` is an optional list of clean
    sources (.epub/.pdf/.docx/.txt or audio) used to fix OCR errors.

    Returns (csv_path, xlsx_path).
    """
    from collections import Counter

    from analytics import build_analytics, summary_lines, write_analytics
    from image_prep import prep_for_ocr
    from obsidian_exporter import export_obsidian
    from pdf_converter import count_pages, input_kind, iter_pages
    from text_utils import writable_path

    if colors is None:
        colors = ALL_COLORS
    if isinstance(references, str):
        references = [references]

    import grammar_corrector
    import llm_corrector as _llm
    grammar_corrector.reset_stats()
    _llm.reset_stats()

    kind = input_kind(input_path)
    total_pages = count_pages(input_path)
    log(f"Input: {kind} · {total_pages or '?'} page(s).")

    # Stage 1: single streaming pass — load, OCR (highlighter-neutralised copy),
    # detect highlights (original colour), assemble passages. Pages are processed
    # one at a time so large image sets don't all sit in RAM, and a bad page is
    # skipped rather than aborting the run.
    results = []
    color_counts = Counter()
    pages_processed = pages_with_hl = 0
    for idx, image in enumerate(iter_pages(input_path, dpi=dpi, log=log)):
        page_num = idx + 1
        log(f"  Page {page_num}{'/' + str(total_pages) if total_pages else ''} ...")
        pages_processed += 1
        try:
            # Accuracy-first OCR: retry with alternate variants when the page
            # reads poorly, keeping the highest-confidence result.
            ocr, variant = run_ocr_best(image, prep_for_ocr(image))
            if variant != "prepped":
                log(f"    low confidence -> retried, kept '{variant}' "
                    f"(conf {ocr.mean_conf})")
        except Exception as e:
            log(f"  ! OCR failed on page {page_num}: {e} — skipping page.")
            continue
        highlights = detect_highlights(image, colors)
        if not highlights:
            continue
        pages_with_hl += 1
        for h in highlights:
            color_counts[h["color"]] += 1

        page_height = image.shape[0]
        for passage in extract_highlight_passages(highlights, ocr.words):
            results.append({
                "page": page_num,
                "highlight_text": passage["text"],
                "before": passage["before"],
                "after": passage["after"],
                "color": passage["color"],
                "mark_phrases": passage["mark_phrases"],
                "ocr_conf": passage["ocr_conf"],
                "start_y": passage["start_y"],
                "end_y": passage["end_y"],
                "start_page_height": page_height,
                "end_page_height": page_height,
                "matched": False,
            })

    log(f"Assembled {len(results)} passage(s) across {pages_with_hl} page(s).")

    # Stage 2-3: load references (resilient), correct text
    sources = _load_sources(references, log)
    _correct_text(results, sources, log)

    # Stage 4: stitch highlights that span a page break (reference confirms
    # contiguity when available; otherwise sentence-cut / geometry heuristics).
    ref_texts = [s["text"] for s in sources if s.get("text")]
    before_merge = len(results)
    results = merge_cross_page(results, ref_texts=ref_texts)
    cross_page_merged = before_merge - len(results)
    if cross_page_merged:
        log(f"  Merged {cross_page_merged} cross-page highlight(s).")

    # Stage 4b: local-LLM repair of real-word OCR errors ("chat" -> "that") on
    # text no reference matched. Guard-railed so quotes are never reworded.
    from config import LLM_MODEL
    todo = [r for r in results if r.get("match_fraction", 0.0) < 1.0]
    if todo and _llm.is_available():
        log(f"  LLM cleanup ({LLM_MODEL}) on {len(todo)} passage(s) "
            f"with unmatched text ...")
        for i, r in enumerate(todo):
            r["highlight_text"] = _llm.llm_fix(r["highlight_text"])
            if (i + 1) % 20 == 0:
                log(f"    ... {i + 1}/{len(todo)}")
        s = _llm.stats
        log(f"  LLM repairs: {s['accepted']} accepted, {s['rejected']} rejected "
            f"by the no-rewording guardrail.")
    elif todo:
        log("  LLM cleanup skipped (Ollama not running or model missing).")

    # Per-highlight confidence (0-100): for the reference-matched share of the
    # passage use the match score (the text was replaced with the book's own
    # wording); for the rest use raw OCR confidence. Low rows get a review flag.
    from config import REVIEW_CONFIDENCE_THRESHOLD
    for r in results:
        f = r.get("match_fraction", 0.0)
        conf = f * r.get("match_score", 0.0) + (1 - f) * r.get("ocr_conf", 0.0)
        r["confidence"] = round(conf, 1)
        r["review"] = conf < REVIEW_CONFIDENCE_THRESHOLD

    for r in results:
        r["parts"] = _build_parts(
            r["before"], r["highlight_text"], r["after"], r["mark_phrases"]
        )

    # Stage 5: exports
    stem, _ext = os.path.splitext(output_path)
    csv_path = writable_path(stem + ".csv")
    xlsx_path = writable_path(stem + ".xlsx")

    export_to_csv(results, csv_path, title=title, author=author)
    log(f"Readwise CSV saved to {csv_path}")
    export_to_excel(results, xlsx_path)
    log(f"Excel workbook saved to {xlsx_path}")

    out_dir = os.path.dirname(os.path.abspath(output_path))
    note_title = title or os.path.splitext(os.path.basename(input_path.rstrip("/\\")))[0]
    archive = _pick_archive_source(sources)
    archive_path, highlights_path, archive_located = export_obsidian(
        results, out_dir, note_title, author=author,
        archive_text=archive["text"] if archive else None,
        source_label=archive["kind"] if archive else "",
        pending=archive is None, log=log,
    )

    # Stage 6: analytics
    analytics_path = writable_path(stem + ".analytics.json")
    matched = sum(1 for r in results if r.get("matched"))
    analytics = build_analytics(
        input_path=input_path, input_kind=kind, pages_total=total_pages,
        pages_processed=pages_processed, pages_with_highlights=pages_with_hl,
        results=results, color_counts=color_counts,
        cross_page_merged=cross_page_merged, reference_matched=matched,
        sources=sources, archive_located=archive_located,
        outputs={"csv": csv_path, "xlsx": xlsx_path, "archive_md": archive_path,
                 "highlights_md": highlights_path, "analytics_json": analytics_path},
        correction_layers={
            "languagetool": dict(grammar_corrector.stats,
                                 available=grammar_corrector.is_available()),
            "llm": dict(_llm.stats, available=_llm.is_available(),
                        model=LLM_MODEL if _llm.is_available() else None),
        },
    )
    write_analytics(analytics, analytics_path)
    log(f"Analytics saved to {analytics_path}")
    for line in summary_lines(analytics):
        log(line)

    return csv_path, xlsx_path


def main():
    # Make console output robust to any Unicode in logs (Windows cp1252).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        description="Extract highlighted text from scanned books "
                    "(PDF or a folder of page photos)."
    )
    parser.add_argument(
        "input", nargs="?",
        help="A PDF, an image, or a folder of page images.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Run an environment self-check (verifies local tools) and exit.",
    )
    parser.add_argument(
        "-o", "--output",
        default="highlights",
        help="Output base name; writes <name>.csv/.xlsx/.analytics.json "
             "(default: highlights).",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Book title for the Readwise CSV (used to group highlights).",
    )
    parser.add_argument(
        "--author",
        default="",
        help="Book author for the Readwise CSV.",
    )
    parser.add_argument(
        "--reference",
        nargs="+",
        default=None,
        metavar="SOURCE",
        help="One or more clean reference sources (.epub/.pdf/.txt, or an audio "
             "file/folder to transcribe). OCR text is corrected against them "
             "(all combined); unmatched text falls back to spell-check.",
    )
    parser.add_argument(
        "-c", "--colors",
        nargs="+",
        choices=ALL_COLORS,
        default=None,
        help=f"Highlight colors to detect (default: all). Choices: {', '.join(ALL_COLORS)}",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help=f"DPI for PDF rendering (default: {DEFAULT_DPI}).",
    )

    args = parser.parse_args()

    if args.check:
        from doctor import check_environment
        sys.exit(0 if check_environment() else 1)

    if not args.input:
        parser.error("the 'input' argument is required (or use --check)")

    try:
        process_pdf(
            args.input, args.output,
            colors=args.colors, dpi=args.dpi,
            title=args.title, author=args.author,
            references=args.reference,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
