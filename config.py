# Global settings for the highlight extractor

# PDF to image conversion
DEFAULT_DPI = 300

# Highlight detection
# The pixel constants below were tuned at DETECT_REFERENCE_WIDTH; at runtime they
# are scaled by (image_width / DETECT_REFERENCE_WIDTH) so the same physical
# highlight is detected identically across scans, photos, and DPI settings.
DETECT_REFERENCE_WIDTH = 1300   # page width (px) the constants were tuned at
MIN_HIGHLIGHT_AREA = 500        # pixels² at reference width - smaller is noise
CLOSE_KERNEL_SIZE = (40, 5)     # bridge gaps along text lines (at reference width)
OPEN_KERNEL_SIZE = (5, 5)       # remove speckle noise (at reference width)

# OCR
OCR_CONFIDENCE_THRESHOLD = 30   # discard words below this confidence
TESSERACT_PSM = 6               # assume single uniform block of text
OCR_PREP_ENABLED = True         # neutralise highlighter colour before OCR (max-channel)
# Accuracy-first OCR retries: if a page's mean word confidence is below this,
# re-OCR with alternate variants (original image, auto-PSM, upscaled) and keep
# the best. Costs extra time only on weak pages.
OCR_RETRY_MIN_CONF = 80
OCR_UPSCALE = 1.5               # upscale factor for the retry variant

# Text matching
WORD_OVERLAP_THRESHOLD = 0.3    # 30% of word width must be inside highlight

# Passage assembly
MAX_PASSAGE_GAP = 12    # highlighted words within this many words join one passage
CONTEXT_WORDS = 20      # words of surrounding context captured for the Note
MIN_PASSAGE_WORDS = 3   # drop shorter passages as detection noise (set 1 to keep all)

# Cross-page merging (join a highlight split across a page break)
PAGE_EDGE_RATIO = 0.18  # within this fraction of top/bottom edge counts as "at the edge"
CROSS_PAGE_BRIDGE_WORDS = 6     # words from each side used to test reference contiguity
CROSS_PAGE_BRIDGE_MIN_SCORE = 85  # fuzzy score (0-100) to accept the bridge as contiguous

# Reference-text correction (align OCR to a clean .epub/.pdf/.txt of the book)
REFERENCE_MIN_SCORE = 76        # accept a LOCAL match (within the in-order window) above this
REFERENCE_REANCHOR_SCORE = 88   # require this much to RE-ANCHOR via a global search (stricter)
REFERENCE_MIN_OCR_CHARS = 28    # don't reference-match shorter fragments (they match spuriously)
REFERENCE_SEARCH_WINDOW = 9000  # chars of reference searched ahead of the cursor
REFERENCE_WINDOW_LOOKBACK = 1500  # chars searched behind the cursor (for slight backtracks)
REFERENCE_LEN_MIN_RATIO = 0.5   # reject if matched span is < this fraction of the OCR length
REFERENCE_LEN_MAX_RATIO = 2.0   # reject if matched span is > this multiple of the OCR length
REFERENCE_MERGE_GAP = 40        # reference chars between two spans to still merge across pages
REFERENCE_GLOBAL_MARGIN = 5     # a global match must beat the window match by this to win

# Per-highlight confidence (0-100): blend of reference match score and OCR word
# confidence. Rows below the threshold are flagged "review" in the XLSX/analytics.
REVIEW_CONFIDENCE_THRESHOLD = 70

# Audio reference transcription (faster-whisper)
# distil-large-v3 is English-only but ~6x faster than large-v3 with near-equal
# accuracy — ideal for long audiobooks (we only need a fuzzy-match reference).
# For non-English audio or maximum accuracy, set this to "large-v3".
AUDIO_MODEL_GPU = "distil-large-v3"  # model used when a CUDA GPU is available
AUDIO_MODEL_CPU = "base"        # smaller/faster model used on CPU fallback
AUDIO_LANGUAGE = "en"           # force language (None = auto-detect, slower)

# Spell-check fallback (only used when no reference match is found)
# Kept conservative: short tokens (e.g. "tech") are valid abbreviations a
# dictionary may flag and wrongly "fix" to a neighbour ("teach"), so skip them.
SPELLCHECK_MIN_WORD_LEN = 5     # ignore short tokens (avoids tech->teach style harm)
SPELLCHECK_MAX_WORD_LEN = 18    # ignore very long tokens (likely OCR garbage / joined words)

# Layered context-aware correction (applied to text no reference matched)
# Layer 1 — LanguageTool (local Java server): deterministic misspelling fixes
# with context ("crip"->"trip"). No-op when Java/LT is unavailable.
GRAMMAR_ENABLED = True
GRAMMAR_MAX_EDIT_DISTANCE = 2   # replacement must be this close to the original word
# Layer 2 — local LLM via Ollama: real-word OCR errors ("chat"->"that").
# Guard-railed: only small word-level substitutions are accepted, so quotes can
# be repaired but never reworded. No-op when Ollama/model is unavailable.
LLM_ENABLED = True
LLM_MODEL = "qwen2.5:3b"
LLM_URL = "http://localhost:11434"
LLM_TIMEOUT = 90                # seconds per passage
LLM_MAX_WORD_EDIT = 2           # max edit distance per substituted word
LLM_MAX_EDITS = 6               # max substituted words per passage (no insert/delete ever)

# Obsidian export (full-text archive + linked highlights note)
ARCHIVE_PARAGRAPH_SENTENCES = 4   # sentences per paragraph in the archived full text
# Which reference becomes the archived full text, best (cleanest) first.
ARCHIVE_SOURCE_PRIORITY = ["epub", "audio", "pdf", "txt", "doc"]
# Detected scan highlight colour -> CSS background. Stays true to the physical
# highlighter colour; renders in Obsidian's <mark> and the Highlightr plugin.
OBSIDIAN_HIGHLIGHT_COLORS = {
    "yellow": "#fff3a3",
    "green":  "#c9f7c0",
    "blue":   "#bfe3ff",
    "pink":   "#ffc0e6",
    "orange": "#ffd8a8",
}
OBSIDIAN_DEFAULT_COLOR = "#fff3a3"  # fallback if a colour isn't in the map above
