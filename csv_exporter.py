"""Stage 5b: Export results to a Readwise-compatible CSV.

Readwise's bulk CSV import (readwise.io/import_bulk) requires a ``Highlight``
column; ``Title``, ``Author``, ``Location`` and ``Note`` are optional. Column
order does not matter and ``Location`` is treated as a numeric position, so the
page number works well there.
"""

import csv

# Separator placed between the leading and trailing context in the Note column.
CONTEXT_SEPARATOR = " […] "

FIELDNAMES = ["Highlight", "Title", "Author", "Location", "Note"]


def _note(result):
    """Context Note: the sentence before and after the highlighted sentence(s)."""
    sides = [s for s in (result.get("before", "").strip(),
                         result.get("after", "").strip()) if s]
    return CONTEXT_SEPARATOR.join(sides)


def export_to_csv(results, output_path, title="", author=""):
    """Write extraction results to a Readwise-compatible CSV file.

    The ``Highlight`` is the sentence(s) containing the highlighted words; the
    ``Note`` carries the surrounding sentence on each side for context.

    Args:
        results: list of dicts with keys page, highlight_text, before, after.
        output_path: path for the .csv file.
        title: book title (Readwise groups highlights by Title/Author).
        author: book author.
    """
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for result in results:
            highlight = result["highlight_text"].strip()
            if not highlight:
                continue

            writer.writerow({
                "Highlight": highlight,
                "Title": title,
                "Author": author,
                "Location": result["page"],
                "Note": _note(result),
            })
