"""
backend/routes/forecast_routes.py

Exposes forecasting and anomaly detection as API endpoints:

    POST /datasets/{id}/forecast -> forecast a numeric column over time
    POST /datasets/{id}/anomalies -> detect row-level + time-series anomalies

Both accept the target column(s) in the request body via Pydantic models
defined here (ForecastRequest, AnomalyRequest), since these need
user-supplied parameters (which columns, how many periods) rather than
just a dataset ID.
"""

import os
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.auth import get_current_user
from backend.models import User
from backend.routes.dataset_routes import _get_owned_dataset_or_404, _read_dataframe
from backend.routes.cleaning_routes import _active_file_path
from backend.services.forecasting import forecast_series
from backend.services.anomaly_detection import detect_anomalies

logger = logging.getLogger("insightai.forecast_routes")

router = APIRouter(prefix="/datasets", tags=["Forecasting & Anomalies"])


class ForecastRequest(BaseModel):
    date_column: str = Field(..., description="Name of the date/time column.")
    value_column: str = Field(..., description="Name of the numeric column to forecast.")
    periods: int = Field(6, ge=1, le=52, description="Number of future periods to forecast.")
    frequency: str = Field("M", pattern="^(D|W|M)$", description="Aggregation frequency: D, W, or M.")


class AnomalyRequest(BaseModel):
    date_column: Optional[str] = Field(None, description="Optional date column for time-series anomaly detection.")
    value_column: Optional[str] = Field(None, description="Optional numeric column paired with date_column.")
    contamination: float = Field(0.05, gt=0.0, lt=0.5, description="Expected proportion of anomalous rows.")


def _load_active_dataframe(dataset_id: int, current_user: User, db: Session):
    """Shared helper: resolves ownership, active file, and loads the DataFrame."""
    dataset = _get_owned_dataset_or_404(dataset_id, current_user, db)
    active_path = _active_file_path(dataset)

    if not os.path.exists(active_path):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="The dataset file is missing from storage.",
        )

    ext = os.path.splitext(active_path)[1].lower()
    return _read_dataframe(active_path, ext)


@router.post("/{dataset_id}/forecast")
def forecast_dataset_route(
    dataset_id: int,
    request: ForecastRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Forecasts a numeric column over time for the given dataset."""
    df = _load_active_dataframe(dataset_id, current_user, db)

    try:
        result = forecast_series(
            df,
            date_col=request.date_column,
            value_col=request.value_column,
            periods=request.periods,
            freq=request.frequency,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    logger.info("User %s forecasted '%s' for dataset %s", current_user.id, request.value_column, dataset_id)

    return {"dataset_id": dataset_id, **result}


@router.post("/{dataset_id}/anomalies")
def detect_dataset_anomalies_route(
    dataset_id: int,
    request: AnomalyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Runs row-level and (optionally) time-series anomaly detection on the dataset."""
    df = _load_active_dataframe(dataset_id, current_user, db)

    try:
        result = detect_anomalies(
            df,
            date_col=request.date_column,
            value_col=request.value_column,
            contamination=request.contamination,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    logger.info("User %s ran anomaly detection on dataset %s", current_user.id, dataset_id)

    return {"dataset_id": dataset_id, **result}
