"""
backend/services/report_generator.py

Report generation service — builds PDF, Excel, or CSV reports summarizing
a dataset's cleaning results, statistics, insights, and charts.

This is the file backend/routes/report_routes.py depends on directly
(generate_report is imported and called there).
"""

import uuid
from pathlib import Path

import pandas as pd
from loguru import logger
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.models import Dataset, ReportFormat
from backend.services.data_analysis import analyze_dataset
from backend.services.data_cleaning import clean_dataset
from backend.services.visualization import generate_all_charts


def _read_dataset_file(file_path: Path) -> pd.DataFrame:
    """Reads a CSV or Excel file into a pandas DataFrame based on its extension."""
    if file_path.suffix.lower() == ".csv":
        return pd.read_csv(file_path)
    return pd.read_excel(file_path)


def _generate_pdf_report(
    df: pd.DataFrame,
    title: str,
    output_path: Path,
    charts_dir: str,
) -> None:
    """Builds a PDF report with a summary table, insights, and embedded charts."""
    _, analysis = clean_dataset(df.copy()), None  # placeholder to keep names local-scoped below
    cleaned_df, cleaning_report = clean_dataset(df.copy())
    analysis = analyze_dataset(cleaned_df)
    chart_paths = generate_all_charts(cleaned_df, charts_dir)

    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=20, spaceAfter=20)
    heading_style = ParagraphStyle("SectionHeading", parent=styles["Heading2"], spaceBefore=16, spaceAfter=8)

    elements: list = []

    elements.append(Paragraph(title, title_style))
    elements.append(Paragraph(
        f"Rows: {cleaning_report.rows_after} &nbsp;&nbsp; Columns: {len(cleaned_df.columns)}",
        styles["Normal"],
    ))
    elements.append(Spacer(1, 0.2 * inch))

    # ---------- Data Cleaning Summary ----------
    elements.append(Paragraph("Data Cleaning Summary", heading_style))
    cleaning_lines = [
        f"Rows before cleaning: {cleaning_report.rows_before}",
        f"Rows after cleaning: {cleaning_report.rows_after}",
        f"Fully empty rows removed: {cleaning_report.rows_dropped_fully_empty}",
        f"Columns with missing values filled: {len(cleaning_report.columns_cleaned)}",
        f"Columns with type corrections: {len(cleaning_report.type_corrections)}",
    ]
    for line in cleaning_lines:
        elements.append(Paragraph(line, styles["Normal"]))
    elements.append(Spacer(1, 0.2 * inch))

    # ---------- Business Insights ----------
    elements.append(Paragraph("Business Insights", heading_style))
    for insight in analysis.insights:
        elements.append(Paragraph(f"&bull; {insight}", styles["Normal"]))
    elements.append(Spacer(1, 0.2 * inch))

    # ---------- Numeric Summary Table ----------
    if analysis.numeric_summary:
        elements.append(Paragraph("Numeric Column Summary", heading_style))
        table_data = [["Column", "Mean", "Median", "Std Dev", "Min", "Max"]]
        for column, stats in analysis.numeric_summary.items():
            table_data.append([
                column,
                f"{stats['mean']:.2f}",
                f"{stats['median']:.2f}",
                f"{stats['std']:.2f}",
                f"{stats['min']:.2f}",
                f"{stats['max']:.2f}",
            ])
        table = Table(table_data, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4C72B0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F0F0F0")]),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.2 * inch))

    # ---------- Charts ----------
    if chart_paths:
        elements.append(Paragraph("Charts", heading_style))
        for chart_path in chart_paths:
            elements.append(Image(chart_path, width=5.5 * inch, height=3.4 * inch))
            elements.append(Spacer(1, 0.15 * inch))

    doc.build(elements)


def _generate_excel_report(df: pd.DataFrame, title: str, output_path: Path) -> None:
    """Builds an Excel report with cleaned data, a summary sheet, and formatting."""
    cleaned_df, cleaning_report = clean_dataset(df.copy())
    analysis = analyze_dataset(cleaned_df)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        cleaned_df.to_excel(writer, sheet_name="Cleaned Data", index=False)

        workbook = writer.book

        # ---------- Summary Sheet ----------
        summary_sheet = workbook.add_worksheet("Summary")
        bold = workbook.add_format({"bold": True, "font_size": 14})
        subheading = workbook.add_format({"bold": True, "font_size": 11, "bg_color": "#D9E1F2"})

        row = 0
        summary_sheet.write(row, 0, title, bold)
        row += 2

        summary_sheet.write(row, 0, "Data Cleaning Summary", subheading)
        row += 1
        cleaning_lines = [
            ("Rows before cleaning", cleaning_report.rows_before),
            ("Rows after cleaning", cleaning_report.rows_after),
            ("Fully empty rows removed", cleaning_report.rows_dropped_fully_empty),
            ("Columns with missing values filled", len(cleaning_report.columns_cleaned)),
        ]
        for label, value in cleaning_lines:
            summary_sheet.write(row, 0, label)
            summary_sheet.write(row, 1, value)
            row += 1
        row += 1

        summary_sheet.write(row, 0, "Business Insights", subheading)
        row += 1
        for insight in analysis.insights:
            summary_sheet.write(row, 0, insight)
            row += 1
        row += 1

        if analysis.numeric_summary:
            summary_sheet.write(row, 0, "Numeric Column Summary", subheading)
            row += 1
            summary_sheet.write_row(row, 0, ["Column", "Mean", "Median", "Std Dev", "Min", "Max"])
            row += 1
            for column, stats in analysis.numeric_summary.items():
                summary_sheet.write_row(row, 0, [
                    column, stats["mean"], stats["median"], stats["std"], stats["min"], stats["max"],
                ])
                row += 1

        summary_sheet.set_column(0, 0, 35)
        summary_sheet.set_column(1, 5, 15)


def _generate_csv_report(df: pd.DataFrame, output_path: Path) -> None:
    """Builds a CSV report containing just the cleaned data (CSV has no room for charts/formatting)."""
    cleaned_df, _ = clean_dataset(df.copy())
    cleaned_df.to_csv(output_path, index=False)


def generate_report(
    dataset: Dataset,
    title: str,
    report_format: ReportFormat,
    upload_dir: str,
    reports_dir: str,
) -> str:
    """
    Generates a report file for a dataset in the requested format.

    Args:
        dataset: The Dataset ORM object (used for its stored_filename).
        title: Human-readable report title, embedded in the output.
        report_format: One of ReportFormat.PDF / EXCEL / CSV.
        upload_dir: Directory where the original uploaded file lives.
        reports_dir: Directory where the generated report should be saved.

    Returns:
        The full file path (as a string) of the generated report.

    Raises:
        ValueError: if the report format is unrecognized.
    """
    source_path = Path(upload_dir) / dataset.stored_filename
    df = _read_dataset_file(source_path)

    reports_path = Path(reports_dir)
    reports_path.mkdir(parents=True, exist_ok=True)

    unique_suffix = uuid.uuid4().hex[:8]

    if report_format == ReportFormat.PDF:
        output_path = reports_path / f"report_{unique_suffix}.pdf"
        _generate_pdf_report(df, title, output_path, charts_dir=str(reports_path / "charts"))
    elif report_format == ReportFormat.EXCEL:
        output_path = reports_path / f"report_{unique_suffix}.xlsx"
        _generate_excel_report(df, title, output_path)
    elif report_format == ReportFormat.CSV:
        output_path = reports_path / f"report_{unique_suffix}.csv"
        _generate_csv_report(df, output_path)
    else:
        raise ValueError(f"Unsupported report format: {report_format}")

    logger.info(f"Generated {report_format.value} report: {output_path}")
    return str(output_path)