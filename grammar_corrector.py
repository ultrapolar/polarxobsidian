"""LanguageTool layer: deterministic spelling/typo fixes with context.

Runs a local LanguageTool server (Java) via ``language_tool_python``. Catches
misspellings the plain frequency spell-checker misses ("crip" -> "trip",
"che" -> "the", "wierd" -> "weird") because LT considers context and has far
richer rules. To protect quotes, only ``misspelling``-type matches are applied,
the chosen replacement must be within a small edit distance of the original
word, and casing is matched to the original.

If Java or LanguageTool is unavailable the layer is a no-op (logged once) —
the pipeline falls back to the plain spell-checker results.
"""

import atexit

from config import GRAMMAR_ENABLED, GRAMMAR_MAX_EDIT_DISTANCE

_tool = None
_unavailable = False

# Per-run counters, surfaced in analytics. Reset via reset_stats().
stats = {"fixes": 0, "checked": 0}


def reset_stats():
    stats["fixes"] = 0
    stats["checked"] = 0


def _get_tool():
    global _tool, _unavailable
    if _tool is not None or _unavailable:
        return _tool
    try:
        import language_tool_python
        _tool = language_tool_python.LanguageTool("en-US")
        atexit.register(_tool.close)
    except Exception:
        _unavailable = True
    return _tool


def is_available():
    return _get_tool() is not None


def _best_replacement(original, replacements):
    """Pick the replacement closest to the original, preferring case-match.

    LT often lists a proper noun first ("Che" before "the"); we prefer the
    candidate whose casing matches the original word and whose edit distance
    is smallest, and reject anything beyond GRAMMAR_MAX_EDIT_DISTANCE.
    """
    from rapidfuzz.distance import Levenshtein

    best, best_key = None, None
    for cand in replacements[:5]:
        if " " in cand:          # never replace one word with several
            continue
        dist = Levenshtein.distance(original.lower(), cand.lower())
        if dist > GRAMMAR_MAX_EDIT_DISTANCE:
            continue
        case_penalty = 0 if (cand[:1].islower() == original[:1].islower()) else 1
        key = (dist, case_penalty)
        if best_key is None or key < best_key:
            best, best_key = cand, key
    if best is None:
        return None
    # Match the original word's casing style.
    if original.isupper():
        return best.upper()
    if original[:1].isupper():
        return best[:1].upper() + best[1:]
    return best


def grammar_fix(text):
    """Return text with LT-detected misspellings conservatively corrected."""
    if not GRAMMAR_ENABLED or not text.strip():
        return text
    tool = _get_tool()
    if tool is None:
        return text

    try:
        matches = tool.check(text)
    except Exception:
        return text

    stats["checked"] += 1
    # Apply right-to-left so earlier offsets stay valid.
    for m in sorted(matches, key=lambda m: m.offset, reverse=True):
        if m.rule_issue_type != "misspelling" or not m.replacements:
            continue
        original = text[m.offset:m.offset + m.error_length]
        if not original or not original.replace("'", "").isalpha():
            continue
        repl = _best_replacement(original, m.replacements)
        if repl is None or repl == original:
            continue
        text = text[:m.offset] + repl + text[m.offset + m.error_length:]
        stats["fixes"] += 1
    return text
