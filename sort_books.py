"""Sort a mixed folder of page photos into per-book folders.

Example:
    python sort_books.py "C:\\Users\\me\\Downloads\\sources" --out sorted ^
        --book "The Compound Effect" "F:\\Audiobooks\\The Compound Effect\\The Compound Effect.mp3" ^
        --book "The Slight Edge" "F:\\Audiobooks\\The Slight Edge\\The Slight Edge.mp3" ^
        --book "Speed Reading"

Each ``--book`` takes the book's title followed by zero or more reference
sources (.epub/.pdf/.txt or audio — audio is transcribed and cached). Titles
are matched against running headers and covers; references against page text.
A ``classification_manifest.json`` is written next to the sorted folders, and
every page is COPIED (originals are never touched).
"""

import argparse
import json
import os
import sys

from book_classifier import Book, classify_pages, sort_into_folders


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        description="Classify a mixed folder of page photos into per-book folders."
    )
    parser.add_argument("folder", help="Folder of page images (mixed books).")
    parser.add_argument(
        "--out", default=None,
        help="Output root for the sorted copies (default: <folder>_sorted).",
    )
    parser.add_argument(
        "--book", action="append", nargs="+", metavar=("TITLE", "REFERENCE"),
        required=True,
        help="Book title followed by optional reference sources. Repeatable.",
    )
    args = parser.parse_args()

    books = [Book(name=b[0], references=list(b[1:])) for b in args.book]
    out_root = args.out or args.folder.rstrip("/\\") + "_sorted"
    os.makedirs(out_root, exist_ok=True)

    results = classify_pages(args.folder, books)
    folders = sort_into_folders(results, out_root)

    manifest = {
        "input": args.folder,
        "books": [{"name": b.name, "references": b.references} for b in books],
        "folders": folders,
        "pages": [
            {"file": os.path.basename(r.file), "session": r.session,
             "label": r.label, "method": r.method, "score": round(r.score, 1)}
            for r in results
        ],
    }
    manifest_path = os.path.join(out_root, "classification_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
