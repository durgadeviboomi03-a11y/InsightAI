"""
backend/routes/forecast_routes.py

Forecasting endpoint:
- POST /forecast — generate a time-series forecast for a numeric column in a dataset
"""

from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.config import get_settings
from backend.database import get_db
from backend.models import Dataset, DatasetStatus, User
from backend.schemas import ForecastRequest, ForecastResponse
from backend.services.forecasting import generate_forecast

router = APIRouter()
settings = get_settings()


def _get_ready_owned_dataset_or_404(dataset_public_id: str, current_user: User, db: Session) -> Dataset:
    """Fetches a dataset owned by the current user, ensuring it's READY for use."""
    dataset = (
        db.query(Dataset)
        .filter(Dataset.public_id == dataset_public_id, Dataset.owner_id == current_user.id)
        .first()
    )
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    if dataset.status != DatasetStatus.READY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset is not ready (status: {dataset.status.value}).",
        )
    return dataset


@router.post("", response_model=ForecastResponse)
def create_forecast(
    payload: ForecastRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ForecastResponse:
    """
    Generates a forecast for a specified value column, using a specified
    date column to establish the time-series ordering.

    Raises:
        404 if the dataset doesn't exist / isn't owned by this user.
        400 if the dataset isn't ready, or the specified columns don't
        exist / aren't the right type (date/numeric).
        500 if forecasting fails unexpectedly.
    """
    dataset = _get_ready_owned_dataset_or_404(payload.dataset_public_id, current_user, db)

    file_path = Path(settings.UPLOAD_DIR) / dataset.stored_filename
    try:
        df = pd.read_csv(file_path) if file_path.suffix == ".csv" else pd.read_excel(file_path)
    except Exception as exc:
        logger.error(f"Failed to read dataset {dataset.public_id} for forecasting: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not read the dataset file.",
        ) from exc

    if payload.date_column not in df.columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Column '{payload.date_column}' does not exist in this dataset.",
        )
    if payload.value_column not in df.columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Column '{payload.value_column}' does not exist in this dataset.",
        )
    if not pd.api.types.is_numeric_dtype(df[payload.value_column]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Column '{payload.value_column}' must be numeric to forecast.",
        )

    try:
        dates, predicted, lower, upper = generate_forecast(
            dataframe=df,
            date_column=payload.date_column,
            value_column=payload.value_column,
            periods_ahead=payload.periods_ahead,
        )
    except Exception as exc:
        logger.error(f"Forecast generation failed for dataset {dataset.public_id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecasting failed: {exc}",
        ) from exc

    logger.info(
        f"Forecast generated for dataset {dataset.public_id} by {current_user.email} "
        f"({payload.periods_ahead} periods ahead)"
    )
    return ForecastResponse(
        dates=dates,
        predicted_values=predicted,
        confidence_lower=lower,
        confidence_upper=upper,
    )