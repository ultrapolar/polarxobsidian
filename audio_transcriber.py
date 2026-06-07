"""Transcribe MP3 (and other) audiobooks to text for use as a reference.

Uses faster-whisper. On Windows the CUDA support DLLs ship as pip packages
(nvidia-cublas-cu12 / nvidia-cudnn-cu12) that aren't on the DLL search path by
default, so we register and preload them before creating a GPU model, and fall
back to CPU if CUDA isn't available.

Transcripts are **cached** next to the audio (``<file>.transcript.txt`` or
``<folder>/_transcript.txt``) because transcription is slow — it runs once per
book and is reused afterwards.
"""

import glob
import json
import os
import re
import site

from config import AUDIO_LANGUAGE, AUDIO_MODEL_CPU, AUDIO_MODEL_GPU

AUDIO_EXTS = (".mp3", ".m4a", ".m4b", ".wav", ".flac", ".ogg", ".aac", ".opus")

_cuda_prepared = False
_last_model_name = None  # set by _make_model, recorded in transcription metadata


# ---------------------------------------------------------------------------
# CUDA DLL setup (Windows pip CUDA libraries)
# ---------------------------------------------------------------------------

def _cuda_dll_dirs():
    bases = []
    try:
        bases += site.getsitepackages()
    except Exception:
        pass
    bases.append(site.getusersitepackages())
    dirs = []
    for base in bases:
        for sub in ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime"):
            d = os.path.join(base, "nvidia", sub, "bin")
            if os.path.isdir(d) and d not in dirs:
                dirs.append(d)
    return dirs


def _prepare_cuda():
    """Register + preload the pip CUDA DLLs. Returns True if they were found."""
    global _cuda_prepared
    if _cuda_prepared:
        return True
    import ctypes

    dirs = _cuda_dll_dirs()
    if not dirs:
        return False

    for d in dirs:
        try:
            os.add_dll_directory(d)
        except (OSError, AttributeError):
            pass
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

    # Preload in dependency order so later LoadLibrary("name") calls resolve.
    for name in ("cublasLt64_12.dll", "cublas64_12.dll", "cudnn64_9.dll"):
        for d in dirs:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                try:
                    ctypes.WinDLL(p)
                except OSError:
                    pass
                break

    _cuda_prepared = True
    return True


def _make_model(log):
    """Create a WhisperModel, preferring CUDA, falling back to CPU."""
    global _last_model_name
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper is required to transcribe audio. Install it with "
            "`pip install faster-whisper` (no internet needed afterwards except "
            "a one-time model download)."
        ) from e

    if _prepare_cuda():
        try:
            model = WhisperModel(AUDIO_MODEL_GPU, device="cuda",
                                 compute_type="float16")
            log(f"  Transcribing on GPU (CUDA) with model '{AUDIO_MODEL_GPU}'.")
            _last_model_name = AUDIO_MODEL_GPU
            return model
        except Exception as e:  # noqa: BLE001 - want any CUDA failure to fall back
            log(f"  CUDA unavailable ({str(e)[:80]}); falling back to CPU.")

    model = WhisperModel(AUDIO_MODEL_CPU, device="cpu", compute_type="int8")
    log(f"  Transcribing on CPU with model '{AUDIO_MODEL_CPU}' "
        f"(slower; install a CUDA GPU for speed).")
    _last_model_name = AUDIO_MODEL_CPU
    return model


# ---------------------------------------------------------------------------
# Audio discovery + caching
# ---------------------------------------------------------------------------

def is_audio(path):
    if os.path.isdir(path):
        return bool(_audio_files(path))
    return path.lower().endswith(AUDIO_EXTS)


def _audio_files(path):
    if os.path.isfile(path):
        return [path]
    files = []
    for ext in AUDIO_EXTS:
        files += glob.glob(os.path.join(path, "**", "*" + ext), recursive=True)
    return sorted(files)


def _cache_path(path):
    if os.path.isdir(path):
        return os.path.join(path, "_transcript.txt")
    return os.path.splitext(path)[0] + ".transcript.txt"


def _meta_path(path):
    return os.path.splitext(_cache_path(path))[0] + ".json"


def transcription_meta(path):
    """Return cached transcription metadata (confidence, duration, model) or None."""
    mp = _meta_path(path)
    if os.path.isfile(mp):
        try:
            with open(mp, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None
    return None


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def transcribe(path, log=print):
    """Return the transcript text for an audio file or folder of audio files.

    Caches the transcript (and a sidecar of confidence/duration metadata) next to
    the source so the slow transcription runs once.
    """
    cache = _cache_path(path)
    if os.path.isfile(cache):
        log(f"  Using cached transcript: {os.path.basename(cache)}")
        with open(cache, encoding="utf-8") as f:
            return f.read()

    files = _audio_files(path)
    if not files:
        raise FileNotFoundError(f"No audio files found at {path}")

    log(f"  Transcribing {len(files)} audio file(s) — this runs once and is cached.")
    model = _make_model(log)

    parts = []
    logprobs = []
    duration = 0.0
    for i, f in enumerate(files):
        log(f"  [{i + 1}/{len(files)}] {os.path.basename(f)} ...")
        segments, info = model.transcribe(
            f, language=AUDIO_LANGUAGE, vad_filter=True
        )
        total = getattr(info, "duration", 0) or 0
        duration += total
        next_mark = 0.0
        for seg in segments:
            parts.append(seg.text)
            if seg.avg_logprob is not None:
                logprobs.append(seg.avg_logprob)
            if total and seg.end >= next_mark:
                pct = min(100, int(100 * seg.end / total))
                log(f"      ...{pct}%")
                next_mark = seg.end + total / 10.0

    text = re.sub(r"\s+", " ", " ".join(parts)).strip()

    # Confidence: mean segment probability (exp of mean avg_logprob), 0-100.
    import math
    confidence = (round(100 * math.exp(sum(logprobs) / len(logprobs)), 1)
                  if logprobs else None)
    meta = {
        "confidence_pct": confidence,
        "duration_sec": round(duration, 1),
        "model": _last_model_name,
        "characters": len(text),
        "files": len(files),
    }

    try:
        with open(cache, "w", encoding="utf-8") as f:
            f.write(text)
        with open(_meta_path(path), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        conf_str = f", confidence {confidence}%" if confidence is not None else ""
        log(f"  Saved transcript ({len(text):,} chars{conf_str}) "
            f"to {os.path.basename(cache)}")
    except OSError as e:
        log(f"  (could not cache transcript: {e})")
    return text
