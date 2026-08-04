"""Stage 5: Export results to Excel with rich text formatting."""

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Font, PatternFill


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
    headers = ["Page", "Passage", "Color", "Confidence", "Review"]
    header_font = Font(bold=True, size=11)
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font

    review_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC",
                              fill_type="solid")

    # Data rows
    for row_idx, result in enumerate(results, start=2):
        ws.cell(row=row_idx, column=1, value=result["page"])

        passage = _build_rich_text(result["parts"])
        ws.cell(row=row_idx, column=2, value=passage)

        ws.cell(row=row_idx, column=3, value=result["color"])
        ws.cell(row=row_idx, column=4, value=result.get("confidence"))
        if result.get("review"):
            flag = ws.cell(row=row_idx, column=5, value="REVIEW")
            flag.font = Font(bold=True, color="9C6500")
            for col in range(1, 6):
                ws.cell(row=row_idx, column=col).fill = review_fill

    # Column widths
    ws.column_dimensions["A"].width = 8   # Page
    ws.column_dimensions["B"].width = 80  # Passage
    ws.column_dimensions["C"].width = 12  # Color
    ws.column_dimensions["D"].width = 11  # Confidence
    ws.column_dimensions["E"].width = 9   # Review

    # Wrap text and top-align for all data rows
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(output_path)
