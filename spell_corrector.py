"""Conservative spell-check fallback for passages with no reference match.

This only fixes tokens the dictionary flags as non-words (e.g. ``cransformation``
-> ``transformation``); it deliberately leaves real words alone, so it will not
"fix" valid words into something else. Case and surrounding punctuation are
preserved. It cannot repair real-word OCR errors (``chat``->``that``) — that is
what reference matching is for.
"""

from config import SPELLCHECK_MAX_WORD_LEN, SPELLCHECK_MIN_WORD_LEN

_spell = None


def _get_spell():
    global _spell
    if _spell is None:
        from spellchecker import SpellChecker
        _spell = SpellChecker(distance=1)  # distance 1 = conservative, fast
    return _spell


def _match_case(correction, original):
    if original.isupper():
        return correction.upper()
    if original[:1].isupper():
        return correction.capitalize()
    return correction


def spell_fix(text):
    """Return text with clearly-misspelled alphabetic tokens corrected."""
    import re

    spell = _get_spell()
    tokens = re.findall(r"[A-Za-z]+|[^A-Za-z]+", text)

    # Collect candidate words (alpha, reasonable length) and look them up once.
    candidates = {
        t.lower()
        for t in tokens
        if t.isalpha()
        and SPELLCHECK_MIN_WORD_LEN <= len(t) <= SPELLCHECK_MAX_WORD_LEN
    }
    unknown = spell.unknown(candidates) if candidates else set()

    out = []
    for t in tokens:
        if t.isalpha() and t.lower() in unknown:
            corr = spell.correction(t.lower())
            if corr and corr != t.lower():
                t = _match_case(corr, t)
        out.append(t)
    return "".join(out)
