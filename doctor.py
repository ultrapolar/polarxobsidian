"""Environment self-check — confirms the pipeline can run fully locally.

Run with:  python main.py --check
"""

import importlib
import shutil


def _status(ok):
    return "OK     " if ok else "MISSING"


def _try_import(mod):
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False


def check_environment(log=print):
    log("Highlight Extractor — environment check")
    log("=" * 44)
    all_ok = True

    required = {
        "numpy": "numpy", "cv2": "opencv-python", "pytesseract": "pytesseract",
        "PIL": "Pillow", "openpyxl": "openpyxl", "pypdf": "pypdf",
        "rapidfuzz": "rapidfuzz", "spellchecker": "pyspellchecker",
        "ebooklib": "EbookLib", "bs4": "beautifulsoup4",
    }
    log("\nPython packages (required):")
    for mod, pip_name in required.items():
        ok = _try_import(mod)
        if not ok and mod in ("numpy", "cv2", "pytesseract", "PIL", "openpyxl"):
            all_ok = False
        log(f"  [{_status(ok)}] {pip_name}")

    log("\nPython packages (optional — only for audiobook references):")
    for mod, pip_name in {"faster_whisper": "faster-whisper"}.items():
        log(f"  [{_status(_try_import(mod))}] {pip_name}")

    log("\nExternal tools:")
    import ocr_engine  # noqa: F401 - configures the Tesseract path on import
    try:
        import pytesseract
        ver = pytesseract.get_tesseract_version()
        log(f"  [{_status(True)}] Tesseract OCR (v{ver})")
    except Exception:
        all_ok = False
        log(f"  [{_status(False)}] Tesseract OCR — install the UB-Mannheim build")

    from pdf_converter import _POPPLER_PATH
    poppler = bool(_POPPLER_PATH or shutil.which("pdftoppm"))
    log(f"  [{_status(poppler)}] Poppler — needed only for PDF input "
        f"(image folders don't require it)")

    log("\nAudio transcription device:")
    try:
        import audio_transcriber
        cuda = audio_transcriber._prepare_cuda()
        log(f"  GPU (CUDA libraries found): {'yes' if cuda else 'no — CPU fallback'}")
    except Exception as e:
        log(f"  faster-whisper not available ({str(e)[:60]})")

    log("\nContext-aware correction layers (optional — used when no reference matches):")
    try:
        import grammar_corrector
        log(f"  [{_status(grammar_corrector.is_available())}] LanguageTool "
            f"(needs Java; deterministic misspelling fixes)")
    except Exception:
        log(f"  [{_status(False)}] LanguageTool")
    try:
        import llm_corrector
        from config import LLM_MODEL
        ok = llm_corrector.is_available()
        log(f"  [{_status(ok)}] Local LLM via Ollama ({LLM_MODEL}; "
            f"real-word OCR fixes, guard-railed)")
    except Exception:
        log(f"  [{_status(False)}] Local LLM via Ollama")

    log("\nEverything runs locally. The only time internet is used is a one-time")
    log("Whisper model download the first time you transcribe an audiobook.")
    log("\n" + ("READY — all required components present."
               if all_ok else "INCOMPLETE — install the MISSING items above."))
    return all_ok
