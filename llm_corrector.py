"""Local-LLM layer: context-aware repair of real-word OCR errors.

A small instruct model served by Ollama (fully local) reads each passage and
fixes errors that only context can reveal — e.g. "well chat is weird" ->
"well that is weird", where "chat" is a real word no spell-checker flags.

The model's output is NEVER trusted blindly. ``_safe_accept`` diffs the
original and proposed text word-by-word and accepts only small word-level
substitutions (each within a tight edit distance) with at most a tiny number
of insertions/deletions. Any paraphrase, reordering, or larger rewrite is
rejected and the original text kept — so a quote can be repaired but never
reworded.

If Ollama isn't running or the model is missing, the layer is a no-op.
"""

import difflib
import json
import re
import urllib.error
import urllib.request

from config import (
    LLM_ENABLED,
    LLM_MAX_EDITS,
    LLM_MAX_WORD_EDIT,
    LLM_MODEL,
    LLM_MODEL_FALLBACKS,
    LLM_TIMEOUT,
    LLM_URL,
)

_available = None       # tri-state: None = unchecked
_resolved_model = None  # the model name actually being used

# Per-run counters, surfaced in analytics. Reset via reset_stats().
stats = {"calls": 0, "accepted": 0, "rejected": 0}

_PROMPT = (
    "The following text was extracted from a scanned book page by OCR and may "
    "contain small recognition errors (for example 'chat' instead of 'that', "
    "'che' instead of 'the', 'cook' instead of 'took'). Correct ONLY clear OCR "
    "errors. Do not rephrase, reorder, add, or remove anything else. Preserve "
    "punctuation and capitalisation. Reply with ONLY the corrected text.\n\n"
    "Text: {text}"
)


def reset_stats():
    stats["calls"] = 0
    stats["accepted"] = 0
    stats["rejected"] = 0


def resolved_model():
    """The model name actually in use (None until is_available() succeeds)."""
    return _resolved_model


def is_available():
    """Check once whether Ollama is up and resolve which model to use.

    The preferred model may not be installed (models get removed, renamed, or
    pulled on a different machine). Rather than silently disabling this whole
    correction layer, fall back through LLM_MODEL_FALLBACKS and finally to any
    installed model — a working small model beats no context-aware correction.
    """
    global _available, _resolved_model
    if _available is not None:
        return _available
    if not LLM_ENABLED:
        _available = False
        return False
    try:
        with urllib.request.urlopen(f"{LLM_URL}/api/tags", timeout=5) as r:
            tags = json.load(r)
        names = [m.get("name", "") for m in tags.get("models", []) if m.get("name")]
    except Exception:
        _available = False
        return False

    for wanted in [LLM_MODEL, *LLM_MODEL_FALLBACKS]:
        for n in names:
            if n == wanted or n.startswith(wanted.split(":")[0] + ":"):
                _resolved_model = n
                _available = True
                return True
    if names:                       # last resort: whatever is installed
        _resolved_model = names[0]
        _available = True
        return True
    _available = False
    return False


def _strip_reasoning(text):
    """Remove <think>...</think> blocks emitted by reasoning models."""
    text = re.sub(r"(?is)<think>.*?</think>", " ", text)
    text = re.sub(r"(?is)^.*?</think>", " ", text)   # unclosed/truncated open tag
    return text.strip()


def _generate(text):
    payload = json.dumps({
        "model": _resolved_model or LLM_MODEL,
        "prompt": _PROMPT.format(text=text),
        "stream": False,
        "think": False,             # ignored by non-reasoning models
        "options": {"temperature": 0},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{LLM_URL}/api/generate", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
        return _strip_reasoning(json.load(r).get("response", ""))


def _safe_accept(original, proposed):
    """Accept only small word-for-word substitutions.

    Insertions and deletions are rejected outright — an OCR misread is a wrong
    word, not a missing one, and a quote must never lose words. Each substituted
    word must be within LLM_MAX_WORD_EDIT of the original.
    """
    from rapidfuzz.distance import Levenshtein

    ow, pw = original.split(), proposed.split()
    if len(ow) != len(pw) or not pw:
        return False

    edits = 0
    sm = difflib.SequenceMatcher(a=[w.lower() for w in ow],
                                 b=[w.lower() for w in pw], autojunk=False)
    for op, a0, a1, b0, b1 in sm.get_opcodes():
        if op == "equal":
            continue
        if op != "replace" or (a1 - a0) != (b1 - b0):
            return False    # any insert/delete or unbalanced block -> reject
        for wa, wb in zip(ow[a0:a1], pw[b0:b1]):
            if Levenshtein.distance(wa.lower(), wb.lower()) > LLM_MAX_WORD_EDIT:
                return False
            edits += 1
        if edits > LLM_MAX_EDITS:
            return False
    return edits > 0


def llm_fix(text):
    """Return LLM-repaired text if the repair passes the guardrail, else text."""
    if not text.strip() or not is_available():
        return text
    stats["calls"] += 1
    try:
        proposed = _generate(text)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return text

    # Strip an echoed "Text:" prefix or wrapping quotes the model may add.
    if proposed.lower().startswith("text:"):
        proposed = proposed[5:].strip()
    if len(proposed) > 2 and proposed[0] == proposed[-1] == '"' and '"' not in text:
        proposed = proposed[1:-1]

    if proposed != text and _safe_accept(text, proposed):
        stats["accepted"] += 1
        return proposed
    if proposed != text:
        stats["rejected"] += 1
    return text
