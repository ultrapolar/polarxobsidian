"""Stage 1: Load pages as numpy arrays — from a PDF, an image, or an image folder."""

import glob
import os
import shutil

import numpy as np
from pdf2image import convert_from_path

from config import DEFAULT_DPI

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")


def _load_image_file(path):
    from PIL import Image
    return np.array(Image.open(path).convert("RGB"))


def _image_files_in(folder):
    files = []
    for name in os.listdir(folder):
        if name.lower().endswith(IMAGE_EXTS):
            files.append(os.path.join(folder, name))
    return sorted(files)


def load_pages(input_path, dpi=DEFAULT_DPI):
    """Load page images (RGB numpy arrays) from any supported input.

    - a folder of images  -> each image is one page, in filename order;
    - a single image file -> one page;
    - a PDF               -> rendered at ``dpi``.
    """
    if os.path.isdir(input_path):
        files = _image_files_in(input_path)
        if not files:
            raise FileNotFoundError(f"No images found in folder: {input_path}")
        return [_load_image_file(f) for f in files]
    if input_path.lower().endswith(IMAGE_EXTS):
        return [_load_image_file(input_path)]
    return convert_pdf_to_images(input_path, dpi=dpi)


def _locate_poppler():
    """Return the Poppler ``bin`` directory, or None if it's already on PATH.

    pdf2image needs Poppler's ``pdftoppm``; the winget package installs it to a
    versioned folder that may not be on PATH in every shell.
    """
    if shutil.which("pdftoppm"):
        return None  # already on PATH; pdf2image will find it

    patterns = [
        os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*Poppler*\**\bin"
        ),
        r"C:\Program Files\poppler*\**\bin",
        r"C:\poppler*\**\bin",
    ]
    for pattern in patterns:
        for path in glob.glob(pattern, recursive=True):
            if os.path.isfile(os.path.join(path, "pdftoppm.exe")):
                return path
    return None


_POPPLER_PATH = _locate_poppler()


def convert_pdf_to_images(pdf_path, dpi=DEFAULT_DPI):
    """Convert each page of a PDF to a numpy array (RGB).

    Args:
        pdf_path: Path to the PDF file.
        dpi: Resolution for rendering. 300 is the sweet spot for OCR accuracy
             and color detection without being excessively slow.

    Returns:
        List of numpy arrays (one per page), in RGB color order.
    """
    kwargs = {"dpi": dpi}
    if _POPPLER_PATH:
        kwargs["poppler_path"] = _POPPLER_PATH
    pil_images = convert_from_path(pdf_path, **kwargs)
    return [np.array(img) for img in pil_images]


def input_kind(input_path):
    """Classify the highlighted-document input: 'images', 'image', or 'pdf'."""
    if os.path.isdir(input_path):
        return "images"
    if input_path.lower().endswith(IMAGE_EXTS):
        return "image"
    return "pdf"


def count_pages(input_path):
    """Best-effort page count without loading everything (for progress/analytics)."""
    if os.path.isdir(input_path):
        return len(_image_files_in(input_path))
    if input_path.lower().endswith(IMAGE_EXTS):
        return 1
    try:
        from pdf2image import pdfinfo_from_path
        kwargs = {"poppler_path": _POPPLER_PATH} if _POPPLER_PATH else {}
        return int(pdfinfo_from_path(input_path, **kwargs)["Pages"])
    except Exception:
        return 0


def _iter_pdf_pages(pdf_path, dpi, log, batch=8):
    """Yield PDF pages as RGB arrays, rendered in small batches to cap memory."""
    kwargs = {"dpi": dpi}
    if _POPPLER_PATH:
        kwargs["poppler_path"] = _POPPLER_PATH
    total = count_pages(pdf_path)
    if total <= 0:  # pdfinfo unavailable — fall back to rendering all at once
        for img in convert_pdf_to_images(pdf_path, dpi=dpi):
            yield img
        return
    for start in range(1, total + 1, batch):
        end = min(start + batch - 1, total)
        try:
            pages = convert_from_path(pdf_path, first_page=start,
                                      last_page=end, **kwargs)
        except Exception as e:  # whole batch failed — log and skip
            log(f"  ! failed to render pages {start}-{end}: {e}")
            continue
        for img in pages:
            yield np.array(img)


def iter_pages(input_path, dpi=DEFAULT_DPI, log=print):
    """Lazily yield page images (RGB arrays) from a PDF, image, or image folder.

    Pages are produced one at a time so large image sets don't all sit in RAM,
    and an unreadable page/image is skipped (logged) instead of aborting the run.
    """
    if os.path.isdir(input_path):
        files = _image_files_in(input_path)
        if not files:
            raise FileNotFoundError(f"No images found in folder: {input_path}")
        for f in files:
            try:
                yield _load_image_file(f)
            except Exception as e:
                log(f"  ! skipping unreadable image {os.path.basename(f)}: {e}")
    elif input_path.lower().endswith(IMAGE_EXTS):
        yield _load_image_file(input_path)
    else:
        yield from _iter_pdf_pages(input_path, dpi, log)
