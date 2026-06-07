"""Export Obsidian notes: a full-text *archive* plus a linked *highlights* note.

The archive note holds the whole book text (from the cleanest available
reference), with the user's highlighted passages marked in their true scan
colour and each given an Obsidian block anchor (``^hl-0001``). The highlights
note quotes each highlight and wiki-links to that anchor, so clicking jumps to
the passage in full context — "smart digital quoting".
"""

import os
import re

from config import (
    ARCHIVE_PARAGRAPH_SENTENCES,
    OBSIDIAN_DEFAULT_COLOR,
    OBSIDIAN_HIGHLIGHT_COLORS,
)
from text_utils import mark_html, writable_path


def _mark(text, phrases):
    """Wrap the exact highlighted phrases in true-colour <mark> tags."""
    return mark_html(text, phrases, OBSIDIAN_HIGHLIGHT_COLORS, OBSIDIAN_DEFAULT_COLOR)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _color_hex(color_str):
    """First detected colour name -> CSS hex."""
    first = (color_str or "").split(",")[0].strip().lower()
    return OBSIDIAN_HIGHLIGHT_COLORS.get(first, OBSIDIAN_DEFAULT_COLOR)


def _sentences_with_offsets(text):
    """Split into (sentence, start, end) keeping character offsets into text."""
    res = []
    start = 0
    for m in re.finditer(r"(?<=[.!?])\s+", text):
        end = m.start()
        if text[start:end].strip():
            res.append((text[start:end], start, end))
        start = m.end()
    if start < len(text) and text[start:].strip():
        res.append((text[start:], start, len(text)))
    return res


def _apply_marks(text, ranges):
    """Wrap (start, end, hex) ranges of text in <mark> tags.

    Same-colour ranges separated only by whitespace are merged into one
    continuous highlight (so a multi-sentence highlight is one mark, not
    several with gaps).
    """
    if not ranges:
        return text
    ranges = sorted(ranges)
    merged = []
    for s, e, c in ranges:
        if merged:
            ps, pe, pc = merged[-1]
            if c == pc and s <= pe:                    # overlapping
                merged[-1] = (ps, max(pe, e), pc)
                continue
            if c == pc and not text[pe:s].strip():     # only whitespace between
                merged[-1] = (ps, e, pc)
                continue
        merged.append((s, e, c))

    out, pos = [], 0
    for s, e, c in merged:
        out.append(text[pos:s])
        out.append(f'<mark style="background: {c};">{text[s:e]}</mark>')
        pos = e
    out.append(text[pos:])
    return "".join(out)


def _yaml(frontmatter):
    lines = ["---"]
    for k, v in frontmatter.items():
        if v is None or v == "":
            continue
        lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines)


def _locate_in_archive(results, archive_text):
    """Find each highlight's character span in the archive text (in order)."""
    from reference_matcher import ReferenceCorrector

    corrector = ReferenceCorrector(archive_text)
    spans = []
    for r in results:
        c = corrector.correct(r["highlight_text"])
        spans.append(c.span if c.matched else None)
    return spans


# ---------------------------------------------------------------------------
# Archive note
# ---------------------------------------------------------------------------

def _build_archive_body(archive_text, results, spans, para_sentences):
    """Return (markdown_body, {result_index: block_id}).

    Highlighted passages become their own anchored blocks; the rest of the book
    flows as paragraphs of ``para_sentences`` sentences each.
    """
    sents = _sentences_with_offsets(archive_text)
    n = len(sents)
    sent_hl = [False] * n
    first_sent_of_result = {}

    for ri, span in enumerate(spans):
        if not span:
            continue
        s0, s1 = span
        covered = [i for i, (_st, sa, sb) in enumerate(sents)
                   if not (sb <= s0 or sa >= s1)]
        for i in covered:
            sent_hl[i] = True
        if covered:
            first_sent_of_result[ri] = covered[0]

    # Block id per run of consecutive highlighted sentences.
    block_of_sent = {}
    counter = 0
    i = 0
    while i < n:
        if sent_hl[i]:
            counter += 1
            bid = f"hl-{counter:04d}"
            while i < n and sent_hl[i]:
                block_of_sent[i] = bid
                i += 1
        else:
            i += 1

    result_block = {
        ri: block_of_sent[s] for ri, s in first_sent_of_result.items()
    }

    # Emit body: non-highlight sentences grouped into paragraphs; each
    # highlighted run emitted as one anchored block with continuous marks.
    body, buffer = [], []

    def flush():
        for p in range(0, len(buffer), para_sentences):
            body.append(" ".join(buffer[p:p + para_sentences]))
        buffer.clear()

    i = 0
    while i < n:
        if not sent_hl[i]:
            buffer.append(sents[i][0])
            i += 1
            continue

        flush()
        bid = block_of_sent[i]
        j = i
        while j < n and block_of_sent.get(j) == bid:
            j += 1
        b_start, b_end = sents[i][1], sents[j - 1][2]
        block_text = archive_text[b_start:b_end]
        # Mark the exact highlighted words (phrases) within this block.
        phrases = []
        for ri, span in enumerate(spans):
            if span and not (span[1] <= b_start or span[0] >= b_end):
                phrases.extend(results[ri].get("mark_phrases", []))
        body.append(_mark(block_text, phrases) + f" ^{bid}")
        i = j
    flush()

    return "\n\n".join(body), result_block


def _build_archive_from_highlights(results):
    """Degraded archive when no reference is available: each highlight is its
    own block (marked OCR text). Returns (body, {result_index: block_id})."""
    body, result_block = [], {}
    for ri, r in enumerate(results):
        bid = f"hl-{ri + 1:04d}"
        text = r["highlight_text"].strip()
        body.append(_mark(text, r.get("mark_phrases", [])) + f" ^{bid}")
        result_block[ri] = bid
    return "\n\n".join(body), result_block


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_obsidian(results, out_dir, title, author="", archive_text=None,
                    source_label="", pending=False, log=print):
    """Write '<title> (full text).md' and '<title> (highlights).md' to out_dir.

    Returns (archive_path, highlights_path).
    """
    title = title or "Highlights"
    archive_name = f"{title} (full text)"
    archive_path = writable_path(os.path.join(out_dir, archive_name + ".md"))
    highlights_path = writable_path(os.path.join(out_dir, f"{title} (highlights).md"))

    if archive_text:
        spans = _locate_in_archive(results, archive_text)
        body, result_block = _build_archive_body(
            archive_text, results, spans, ARCHIVE_PARAGRAPH_SENTENCES
        )
        located = sum(1 for ri in range(len(results)) if ri in result_block)
        log(f"  Obsidian: located {located}/{len(results)} highlights in the "
            f"archive ({source_label}).")
    else:
        body, result_block = _build_archive_from_highlights(results)
        located = 0
        pending = True

    status = "pending-review" if pending else "verified"

    # Archive note
    archive_fm = _yaml({
        "title": title,
        "author": author,
        "source": source_label or "OCR (no reference)",
        "type": "source/full-text",
        "status": status,
        "tags": "[book, source]",
    })
    archive_md = (
        f"{archive_fm}\n\n# {title} — Full Text\n\n"
        f"> [!quote] Archived source ({source_label or 'OCR'}) — "
        f"highlights marked inline.\n\n{body}\n"
    )
    with open(archive_path, "w", encoding="utf-8") as f:
        f.write(archive_md)

    # Highlights note
    hl_fm = _yaml({
        "title": f"{title} (highlights)",
        "author": author,
        "status": status,
        "highlights": len(results),
        "tags": "[book, highlights]",
    })
    from text_utils import smart_join

    lines = [hl_fm, "", f"# {title} — Highlights", ""]
    for ri, r in enumerate(results):
        # Highlight in its sentence context (seams de-duplicated), with the exact
        # highlighted words marked.
        before = " ".join(r.get("before", "").split())
        after = " ".join(r.get("after", "").split())
        full = smart_join(smart_join(before, " ".join(r["highlight_text"].split())),
                          after)
        quote = _mark(full, r.get("mark_phrases", []))
        lines.append(f"> [!quote] p.{r['page']}")
        lines.append(f"> {quote}")
        bid = result_block.get(ri)
        if bid:
            lines.append(">")
            lines.append(f"> → [[{archive_name}#^{bid}|full context]]")
        lines.append("")
    with open(highlights_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log(f"  Obsidian archive  -> {archive_path}")
    log(f"  Obsidian highlights -> {highlights_path}")
    return archive_path, highlights_path, located
