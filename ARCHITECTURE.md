# Architecture & module reference

A local pipeline that pulls **highlighted text** out of scanned/photographed book
pages and exports it for Readwise (CSV), review (XLSX), and Obsidian (a full-text
archive + a linked highlights note). Everything runs on your machine; the only
network use is a one-time Whisper model download for audiobook references.

## Pipeline at a glance

```
input (PDF | image | image folder)
  │
  ▼  pdf_converter.iter_pages           lazy, per-page, resilient
  ▼  image_prep.prep_for_ocr            max-channel: neutralise highlighter for OCR
  ▼  ocr_engine.run_ocr                 Tesseract -> words + boxes  (on the prepped copy)
  ▼  highlight_detector.detect_highlights   HSV colour masks         (on the ORIGINAL colour)
  ▼  text_matcher.extract_highlight_passages   sentence-aware passages + mark phrases
  │
  ▼  reference_matcher (+ audio_transcriber, spell_corrector)
  │      correct OCR text against the combined references, else spell-check
  ▼  page_merger.merge_cross_page       stitch quotes split across a page break
  │
  ├─▶ csv_exporter      -> <out>.csv            (Readwise)
  ├─▶ excel_exporter    -> <out>.xlsx           (review; highlighted words bold)
  ├─▶ obsidian_exporter -> "<Title> (full text).md" + "<Title> (highlights).md"
  └─▶ analytics         -> <out>.analytics.json (+ printed summary)
```

`main.process_pdf()` is the orchestrator that runs all of the above.

## Entry points

| File | What it is |
|---|---|
| `main.py` | CLI + `process_pdf()` orchestrator. `python main.py <input> -o <out> [--reference ...] [--title ...] [--check]`. |
| `gui.py` | Minimal Tkinter GUI: pick a **PDF** or **image folder**, add reference sources (file/audio folder), Extract, or Transcribe-only. Runs the pipeline on a worker thread. |
| `transcribe.py` | Batch audiobook → cached transcript, no PDF. `python transcribe.py <audio...>`. |
| `doctor.py` | `python main.py --check` — verifies local tools (Tesseract, Poppler, faster-whisper, GPU) and confirms offline operation. |

## Stage modules

### Input loading — `pdf_converter.py`
- `iter_pages(input_path, dpi)` — **generator** yielding RGB page arrays. Folder of
  images → one page per file (sorted); single image → one page; PDF → rendered in
  small batches (low memory). Unreadable pages/images are skipped (logged).
- `input_kind()`, `count_pages()` — for progress/analytics.
- Auto-locates **Poppler** (PDF rendering) if not on PATH.

### OCR preprocessing — `image_prep.py`
- `prep_for_ocr(image)` — text is dark in every channel, a highlighter is light &
  coloured, so the **per-pixel max of R/G/B** turns the highlighter near-white while
  keeping text dark. Plus denoise + CLAHE. This is what lets highlighted words OCR
  cleanly. Detection still uses the original colour image. Toggle: `OCR_PREP_ENABLED`.

### OCR — `ocr_engine.py`
- `run_ocr(image, psm)` → `OCRResult(full_text, words, mean_conf)`, each `OCRWord`
  carrying text + bounding box + block/par/line indices + Tesseract confidence.
  Auto-locates **Tesseract** on Windows. Single Tesseract pass per call.
- `run_ocr_best(image, prepped)` — accuracy-first: if the prepped image reads
  below `OCR_RETRY_MIN_CONF`, retries with the original image, auto-PSM (3), and
  a 1.5× upscale (boxes mapped back), keeping the highest mean confidence.

### Highlight detection — `highlight_detector.py` + `color_profiles.py`
- `detect_highlights(image, colors)` — HSV `inRange` per colour + morphology →
  bounding boxes (color, bbox). `color_profiles.HIGHLIGHT_PROFILES` holds the HSV
  ranges for yellow/green/pink/blue/orange (tuned to ignore yellowed paper).
- Pixel constants (`MIN_HIGHLIGHT_AREA`, kernels) are defined at
  `DETECT_REFERENCE_WIDTH` and **scaled to the actual image width**, so scans,
  photos, and different DPIs detect the same physical highlight identically.

### Passage assembly — `text_matcher.py`
- `extract_highlight_passages(highlights, ocr_words)` — the heart of "what is a
  highlight". Maps highlight boxes → OCR words, then builds **sentence-aware**
  passages: the highlighted sentence(s) (consecutive ones merged), plus one
  sentence of context each side (`before`/`after`), plus `mark_phrases` (the exact
  highlighted word-runs) so the precise words can still be marked. Returns dicts:
  `text, before, after, color, mark_phrases, start_y, end_y`.

### Text correction — `reference_matcher.py`, `audio_transcriber.py`, `spell_corrector.py`
- `load_reference_text(path)` — load a reference to plain text. `.epub` (ebooklib →
  unzip fallback), `.pdf` (pypdf → `pdftotext` fallback), `.docx`, `.txt`
  (multi-encoding), or **audio** (transcribed). Each has a fallback.
- `audio_transcriber.transcribe(path)` — faster-whisper, **GPU→CPU** fallback,
  cached to `*.transcript.txt` (+ a `.json` of confidence/duration/model). Handles
  a single file or a folder of chapter files. CUDA DLLs are preloaded on Windows.
- `ReferenceCorrector` — fuzzy-aligns one sentence to one reference. Searches
  BOTH the in-order window ahead of the cursor and the whole book; the window
  match wins unless the global match is clearly better (`REFERENCE_GLOBAL_MARGIN`),
  and a global-only match must clear the stricter re-anchor bar. Length guard
  rejects spurious spans.
- `MultiReferenceCorrector.correct_passage()` — splits a passage into sentences and
  matches **each sentence against every reference**, keeping the best confident hit;
  unmatched sentences fall back to `spell_corrector.spell_fix` (conservative —
  only fixes clear non-words). Seams de-duplicated via `text_utils.smart_join`.

### Cross-page merge — `page_merger.py`
- `merge_cross_page(results, ref_texts)` — stitches a quote split across a page
  break (consecutive pages). Three signals, strongest first: **reference bridge**
  ("prev tail + cur head" appears contiguously in a reference), **cut sentence**
  (prev ends mid-sentence), **geometry** (bottom-edge → top-edge). If both halves
  matched the reference but don't bridge, they're left separate.

### Shared helpers — `text_utils.py`
- `smart_join(a, b)` — concatenate, trimming a duplicated word run at the seam.
- `locate_phrases / mark_html / bold_parts` — find the highlighted phrases inside a
  (possibly corrected) text and wrap/bold them, snapping to word boundaries.
- `writable_path(path)` — returns a free name if the target is locked (open in Excel).

### Exporters
- `csv_exporter.py` — Readwise CSV: `Highlight` = the highlighted sentence(s),
  `Note` = the before/after context sentences, `Location` = page.
- `excel_exporter.py` — `.xlsx` with the passage in context, highlighted words bold.
- `obsidian_exporter.py` — two notes. **Archive** = the whole book (from the best
  reference by the `epub > audio > pdf > txt` waterfall) with highlighted words in
  true-colour `<mark>` tags + block anchors (`^hl-0001`). **Highlights** note =
  each quote (context + marks) wiki-linked to its anchor. No reference ⇒ archive is
  built from the OCR text and stamped `status: pending-review`.

### Analytics — `analytics.py`
- Writes `<out>.analytics.json` and a printed summary: pages processed/with
  highlights, total highlights + per-colour breakdown + avg length, cross-page
  merges, reference match rate, archive link count, each reference's char count +
  load status, and audiobook transcription confidence + model.

### Settings — `config.py`
All tunable knobs live here, grouped by stage: DPI, HSV ranges (in
`color_profiles.py`), OCR confidence/PSM, `OCR_PREP_ENABLED`, passage gaps,
`PAGE_EDGE_RATIO` + cross-page bridge thresholds, reference-match thresholds,
Whisper models, spell-check bounds, Obsidian colours/priority.

## The `result` dict (flows from assembly to export)

```
page, highlight_text, before, after, color, mark_phrases, ocr_conf,
match_score, match_fraction, confidence, review,
start_y, end_y, start_page_height, end_page_height, matched, parts, spans_pages?
```

`mark_phrases` is a list of `(phrase, colour_name)`; `parts` is the
`[(text, is_bold)]` the exporters render; `matched` flags reference-corrected.

**Per-highlight confidence** (0-100): `confidence = match_fraction × match_score
+ (1 − match_fraction) × ocr_conf` — the reference-matched share of a passage is
scored by its fuzzy-match quality (the text was replaced with the book's own
wording), the rest by raw Tesseract word confidence. Rows below
`REVIEW_CONFIDENCE_THRESHOLD` get `review=True` → highlighted "REVIEW" rows in
the XLSX and a `review_rows` list in the analytics JSON. The Readwise CSV stays
clean (no extra columns).

## Running locally

`pip install -r requirements.txt`, install Tesseract + Poppler (see `README.md`),
then `python main.py --check`. GPU transcription uses pip CUDA libs
(`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`); CPU works without them.
