"""
backend/routes/report_routes.py

Exposes downloadable report generation:

    GET /datasets/{id}/report/pdf   -> generates and downloads a PDF report
    GET /datasets/{id}/report/xlsx  -> generates and downloads an Excel report

Forecast is optional and only included if valid date_column/value_column
query parameters are supplied (since forecasting requires user-chosen
columns, unlike overview/charts which are fully automatic).
"""

import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.auth import get_current_user
from backend.models import User
from backend.routes.dataset_routes import _get_owned_dataset_or_404, _read_dataframe
from backend.routes.cleaning_routes import _active_file_path
from backend.services.data_analysis import analyze_dataset
from backend.services.visualization import generate_visualizations
from backend.services.forecasting import forecast_series
from backend.services.anomaly_detection import detect_anomalies
from backend.services.report_generator import generate_pdf_report, generate_excel_report

logger = logging.getLogger("insightai.report_routes")

router = APIRouter(prefix="/datasets", tags=["Reports"])


def _load_dataset_and_overview(dataset_id: int, current_user: User, db: Session):
    """Shared setup: ownership check, load active file, run overview analysis."""
    dataset = _get_owned_dataset_or_404(dataset_id, current_user, db)
    active_path = _active_file_path(dataset)

    if not os.path.exists(active_path):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="The dataset file is missing from storage.",
        )

    ext = os.path.splitext(active_path)[1].lower()
    df = _read_dataframe(active_path, ext)

    try:
        overview = analyze_dataset(df)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return dataset, df, overview


def _optional_forecast(df, date_column: Optional[str], value_column: Optional[str]):
    """Returns a forecast dict if both columns are provided and valid, else None."""
    if not date_column or not value_column:
        return None
    try:
        return forecast_series(df, date_col=date_column, value_col=value_column, periods=6, freq="M")
    except ValueError as exc:
        logger.warning("Skipping forecast section in report: %s", exc)
        return None


def _optional_anomalies(df, date_column: Optional[str], value_column: Optional[str]):
    """Always attempts row-level anomalies; adds time-series if columns are valid."""
    try:
        return detect_anomalies(df, date_col=date_column, value_col=value_column)
    except ValueError as exc:
        logger.warning("Skipping anomaly section in report: %s", exc)
        return None


@router.get("/{dataset_id}/report/pdf")
def download_pdf_report(
    dataset_id: int,
    date_column: Optional[str] = Query(None, description="Optional date column for forecast/anomaly sections."),
    value_column: Optional[str] = Query(None, description="Optional numeric column paired with date_column."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates and downloads a PDF report for the dataset."""
    dataset, df, overview = _load_dataset_and_overview(dataset_id, current_user, db)

    try:
        charts = generate_visualizations(df)
    except ValueError:
        charts = None

    forecast = _optional_forecast(df, date_column, value_column)
    anomalies = _optional_anomalies(df, date_column, value_column)

    pdf_path = generate_pdf_report(
        dataset_name=dataset.original_filename,
        overview=overview,
        charts=charts,
        forecast=forecast,
        anomalies=anomalies,
    )

    logger.info("User %s downloaded PDF report for dataset %s", current_user.id, dataset_id)

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=os.path.basename(pdf_path),
    )


@router.get("/{dataset_id}/report/xlsx")
def download_excel_report(
    dataset_id: int,
    date_column: Optional[str] = Query(None, description="Optional date column for forecast/anomaly sections."),
    value_column: Optional[str] = Query(None, description="Optional numeric column paired with date_column."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generates and downloads an Excel report for the dataset."""
    dataset, df, overview = _load_dataset_and_overview(dataset_id, current_user, db)

    forecast = _optional_forecast(df, date_column, value_column)
    anomalies = _optional_anomalies(df, date_column, value_column)

    xlsx_path = generate_excel_report(
        dataset_name=dataset.original_filename,
        overview=overview,
        forecast=forecast,
        anomalies=anomalies,
    )

    logger.info("User %s downloaded Excel report for dataset %s", current_user.id, dataset_id)

    return FileResponse(
        path=xlsx_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=os.path.basename(xlsx_path),
    )
