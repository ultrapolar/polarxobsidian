# PDF Highlight Extractor → Readwise

Extracts highlighted text from **scanned / photographed** book PDFs and exports it
as a CSV that [Readwise](https://readwise.io) can import. Because it works from the
page image (OCR + highlighter-color detection), it does **not** need embedded Adobe
highlight annotations — it works on photos and scans.

For each highlighted passage it produces one row: the highlighted text in the
`Highlight` column, the surrounding sentences in the `Note` column, the page number
in `Location`, plus the `Title`/`Author` you supply. A formatted `.xlsx` (with the
highlights bolded in context) is written alongside the CSV for your own review.

## Requirements

### Python packages

```
pip install -r requirements.txt
```

### External programs

The pipeline shells out to two non-Python tools:

- **Tesseract OCR** — used by `pytesseract` to read the text.
  Windows installer: https://github.com/UB-Mannheim/tesseract/wiki
  (or `winget install UB-Mannheim.TesseractOCR`)
- **Poppler** — used by `pdf2image` to rasterize PDF pages.
  Windows builds: https://github.com/oschwartz10612/poppler-windows/releases
  (or `winget install oschwartz10612.Poppler`)

You do **not** have to add these to your PATH manually: on startup the program
auto-detects Tesseract (`C:\Program Files\Tesseract-OCR\…`) and Poppler (the
winget install location), so installing them is enough. If you put them
somewhere custom, add that folder to PATH and they'll be found there.

### Check your setup

```
python main.py --check
```

Verifies every dependency (Python packages, Tesseract, Poppler, faster-whisper +
GPU) and prints what's missing.

### Everything runs locally

All processing — OCR, highlight detection, reference matching, audio
transcription — happens on your machine. The **only** time the internet is used
is a one-time Whisper model download the first time you transcribe an audiobook;
after that it is fully offline. Each input and reference type has a fallback (a
failed/garbled reference is skipped rather than aborting the run; an unreadable
page is skipped; PDF text falls back from pypdf to `pdftotext`; EPUB/DOCX fall
back to a direct unzip; audio falls back from GPU to CPU).

## Usage

### Input: PDF or a folder of photos

The input can be a **scanned PDF** *or* a **folder of page images** (phone photos
/ scans, `.jpg`/`.png`/…). For a folder, each image is one page in filename order.
Highlighter colour is neutralised before OCR (a per-pixel max-channel pass) so the
text *under* a highlight reads as cleanly as the rest — important for photos where
the highlighter otherwise dims its own text.

### GUI (recommended)

```
python gui.py
```

Pick **PDF…** or **Image folder…**, fill in **Title** and **Author**, then click
**Extract highlights**. Progress streams in the status box; when it finishes you'll
get `<pdf-name>.csv` and `<pdf-name>.xlsx` next to the original PDF.

### Command line

```
python main.py path/to/book.pdf -o out --title "Book Title" --author "Author Name"
```

Writes `out.csv` and `out.xlsx`. Useful flags:

- `--title` / `--author` — book metadata for Readwise grouping.
- `--reference path/to/book.epub` — clean ebook/text used to fix OCR errors
  (see below).
- `-c/--colors` — limit detection to specific highlighter colors
  (choices: yellow, green, pink, blue, orange; default: all).
- `--dpi` — rendering resolution (default 300).

## Fixing OCR errors with a reference ebook (recommended)

OCR on scanned pages produces errors, and many are *real words* (e.g. `chat`
instead of `that`, `che` instead of `the`) that a spell-checker cannot catch. If
you have a clean copy of the book, provide it as a **reference** and the program
will fuzzy-align each highlight — sentence by sentence — to the real text and
replace the OCR output with the original wording.

Supported reference sources (provide **one or more**, they're combined):

- `.epub`, `.txt`, or a **text-based** `.pdf` (a *scanned* PDF won't work — no
  selectable text).
- **Audiobook** audio: an `.mp3`/`.m4b`/… file, or a **folder** of them. The audio
  is transcribed to text with [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  and the transcript is cached next to the audio (`*.transcript.txt`) so it only
  runs once. With an NVIDIA GPU it's fast; on CPU it's slower but works.

How to provide them:

- **GUI:** the *References (optional)* box — **Add file…** for ebook/PDF/text/audio,
  or **Add audio folder…** for a multi-file audiobook. Add as many as you like.
- **CLI:** `--reference book.epub audiobook_folder` (space-separated list).

Combining sources gives the best coverage: a sentence the PDF's edition reworded
may match the audiobook, and vice-versa. Each sentence is replaced only when it
confidently matches a source; otherwise it falls back to a conservative
spell-check. Highlights split across a page break are rejoined automatically.

### Transcribing audiobooks separately (batch / overnight)

Transcription runs automatically the first time you use an audiobook as a
reference, but you can also do it ahead of time:

- **GUI:** the **Transcribe audio only…** button — pick one or more audio files,
  no PDF needed.
- **CLI:** `python transcribe.py book1.mp3 "D:\Audiobooks\Deep Work" ...`
  (each path is one book; a folder is treated as chapters of one book).

Either way the transcript is cached next to the audio (`*.transcript.txt`), so
the later highlight extraction reuses it instantly. Good for kicking off a batch
of long books overnight.

**Edition matters.** Matching is fuzzy, so a *different* edition still helps — but
only sentences whose wording is identical across editions get corrected (often
~20–40%). A reference of the **same edition** as your scanned book (or its
unabridged audiobook) corrects the large majority.

Without a reference, the program still runs — text falls through three layered
local correctors instead:

1. **Spell-check** (non-words: `cransformation` → `transformation`),
2. **LanguageTool** (context-aware misspellings: `crip` → `trip`, `che` → `the`;
   needs Java — already a no-op if missing),
3. **Local LLM via Ollama** (real-word OCR errors only context reveals:
   `chat` → `that`; guard-railed to word-for-word substitutions so quotes are
   never reworded or shortened; needs Ollama + the model in `config.LLM_MODEL`).

All three are local. A reference is still the gold standard — these layers are
the safety net, and remaining doubt shows up as REVIEW flags in the XLSX.

## Obsidian notes (full-text archive + linked highlights)

Alongside the CSV/XLSX, every run writes two Obsidian-flavored Markdown notes:

- **`<Title> (full text).md`** — the whole book (from the cleanest reference) with
  your highlighted passages marked inline in their **true scan colour** (via
  `<mark>` tags that render in Obsidian and the Highlightr plugin). Each
  highlighted passage gets a block anchor (`^hl-0001`).
- **`<Title> (highlights).md`** — each highlight as a `> [!quote]` callout that
  wiki-links to its anchor in the archive (`[[<Title> (full text)#^hl-0001]]`), so
  clicking jumps you to the passage in full context.

The archive's full text is chosen by priority: **epub → audiobook → source PDF →
txt/doc**. If no reference is supplied, the archive is built from the (spell-checked)
OCR text only and stamped `status: pending-review` in the frontmatter.

Drop both notes into your vault — they inherit your theme automatically. Colours
are configurable in `config.py` (`OBSIDIAN_HIGHLIGHT_COLORS`).

## Analytics

Every run writes `<output>.analytics.json` (and prints a summary) with metrics
for post-processing: pages processed / with highlights, total highlights and a
per-colour breakdown, cross-page merges, reference-correction match rate, archive
link count, each reference's character count + load status, and — for audiobooks
— the transcription confidence (mean Whisper segment probability) and model used.

## Importing to Readwise

Upload the generated `.csv` at <https://readwise.io/import_bulk>. Highlights are
grouped under the Title/Author you provided, with the context in each Note.

## Tuning (for scanned/photographed pages)

Highlight detection on scans is imperfect: faint highlighter, low-resolution
scans, and OCR errors all reduce quality. The knobs in `config.py` let you trade
off precision vs. recall:

- `HIGHLIGHT_PROFILES` (in `color_profiles.py`) — HSV color ranges per highlighter
  color. Widen a range if a color is being missed; narrow it if page color/noise
  is falsely detected.
- `WORD_OVERLAP_THRESHOLD` — how much of a word must sit under a highlight to count
  (lower = catches more words on faint highlights, but more false positives).
- `MAX_PASSAGE_GAP` — how many words may separate two highlighted words before they
  split into separate rows (higher = keeps long passages together across patchy
  detection; too high merges unrelated highlights).
- `MIN_PASSAGE_WORDS` — drops passages shorter than this as noise (set to `1` to
  keep every detected fragment).
- `OCR_CONFIDENCE_THRESHOLD` / `DEFAULT_DPI` — OCR sensitivity and render
  resolution.

Because OCR is not perfect on scans, expect to lightly proofread the output before
or after importing. The `.xlsx` (highlights shown bold in context) is the easiest
place to review.
