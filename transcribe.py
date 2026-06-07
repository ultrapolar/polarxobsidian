"""Batch-transcribe audiobooks to cached text — no PDF needed.

Each path is treated as one book: a single audio file, or a folder of chapter
files (combined in name order). The transcript is written next to the source as
``<file>.transcript.txt`` (or ``<folder>/_transcript.txt``) and reused by the
highlight extractor later, so you can pre-transcribe a batch overnight.

Examples:
    python transcribe.py "F:\\Audiobooks\\The Slight Edge\\The Slight Edge.mp3"
    python transcribe.py "D:\\Books\\Atomic Habits"        # folder of chapters
    python transcribe.py book1.mp3 book2.m4b "D:\\Books\\Deep Work"
"""

import argparse
import sys

from audio_transcriber import is_audio, transcribe


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audiobook(s) to cached text files."
    )
    parser.add_argument(
        "paths", nargs="+",
        help="Audio file(s) or folder(s); each is treated as one book.",
    )
    args = parser.parse_args()

    failures = 0
    for path in args.paths:
        if not is_audio(path):
            print(f"Skipping (no audio found): {path}", file=sys.stderr)
            failures += 1
            continue
        print(f"=== {path} ===")
        try:
            text = transcribe(path)
            print(f"  done: {len(text):,} characters\n")
        except Exception as e:  # keep going through the batch
            print(f"  ERROR: {e}\n", file=sys.stderr)
            failures += 1

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
