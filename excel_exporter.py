"""Stage 5: Export results to Excel with rich text formatting."""

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Font


def _build_rich_text(parts):
    """Convert a list of (text, is_bold) tuples into an openpyxl CellRichText.

    If there's only one part and it's not bold, returns a plain string instead
    (openpyxl requires at least one InlineFont segment for CellRichText).
    """
    if not parts:
        return ""

    # If nothing is bold, return plain string
    if not any(bold for _, bold in parts):
        return "".join(text for text, _ in parts)

    segments = []
    for text, is_bold in parts:
        if not text:
            continue
        if is_bold:
            segments.append(
                TextBlock(InlineFont(b=True), text)
            )
        else:
            segments.append(
                TextBlock(InlineFont(), text)
            )

    if not segments:
        return ""

    return CellRichText(*segments)


def export_to_excel(results, output_path):
    """Write extraction results to an Excel file.

    Args:
        results: list of dicts, each with keys:
            - page: int
            - parts: list of (text, is_bold) tuples
            - color: str
        output_path: path for the .xlsx file.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Highlights"

    # Headers
    headers = ["Page", "Passage", "Color"]
    header_font = Font(bold=True, size=11)
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font

    # Data rows
    for row_idx, result in enumerate(results, start=2):
        ws.cell(row=row_idx, column=1, value=result["page"])

        passage = _build_rich_text(result["parts"])
        ws.cell(row=row_idx, column=2, value=passage)

        ws.cell(row=row_idx, column=3, value=result["color"])

    # Column widths
    ws.column_dimensions["A"].width = 8   # Page
    ws.column_dimensions["B"].width = 80  # Passage
    ws.column_dimensions["C"].width = 12  # Color

    # Wrap text and top-align for all data rows
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(output_path)
