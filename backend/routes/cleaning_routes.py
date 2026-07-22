"""
backend/routes/cleaning_routes.py

Routes that tie together dataset storage, cleaning, and analysis:

    POST /datasets/{id}/clean    -> clean the dataset, persist a cleaned copy,
                                     return the cleaning report
    GET  /datasets/{id}/overview -> run analyze_dataset() on the (cleaned, if
                                     available) file and return the overview

These routes assume dataset_routes.py's Dataset model and helpers
(_get_owned_dataset_or_404, _read_dataframe) are importable from that module.
"""

import os
import logging

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Column, String, Boolean
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.auth import get_current_user
from backend.models import User
from backend.routes.dataset_routes import (
    Dataset,
    _get_owned_dataset_or_404,
    _read_dataframe,
    UPLOAD_DIR,
)
from backend.services.data_cleaning import clean_dataset, CleaningConfig
from backend.services.data_analysis import analyze_dataset

logger = logging.getLogger("insightai.cleaning_routes")

router = APIRouter(prefix="/datasets", tags=["Cleaning & Analysis"])

# --------------------------------------------------------------------------
# NOTE on schema change:
# This assumes two new columns exist on the Dataset model (add these to the
# Dataset class in dataset_routes.py, or a migration if you're using Alembic):
#
#     cleaned_file_path = Column(String(500), nullable=True)
#     is_cleaned        = Column(Boolean, default=False, nullable=False)
#
# If you'd rather not touch the model, tell me and I'll store the cleaned
# file path in a separate small table instead.
# --------------------------------------------------------------------------


def _active_file_path(dataset: Dataset) -> str:
    """Returns the cleaned file path if one exists, otherwise the original."""
    cleaned_path = getattr(dataset, "cleaned_file_path", None)
    if cleaned_path and os.path.exists(cleaned_path):
        return cleaned_path
    return dataset.file_path


@router.post("/{dataset_id}/clean")
def clean_dataset_route(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Cleans the dataset using default strategies, saves the cleaned version
    alongside the original, and returns the cleaning report.
    """
    dataset = _get_owned_dataset_or_404(dataset_id, current_user, db)

    if not os.path.exists(dataset.file_path):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="The original file is missing from storage.",
        )

    ext = os.path.splitext(dataset.file_path)[1].lower()
    df = _read_dataframe(dataset.file_path, ext)

    try:
        result = clean_dataset(df, CleaningConfig())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    cleaned_df = result["cleaned_df"]
    report = result["report"]

    cleaned_filename = f"cleaned_{os.path.basename(dataset.file_path)}"
    cleaned_path = os.path.join(UPLOAD_DIR, cleaned_filename)

    try:
        if ext == ".csv":
            cleaned_df.to_csv(cleaned_path, index=False)
        else:
            cleaned_df.to_excel(cleaned_path, index=False)
    except OSError as exc:
        logger.error("Failed to write cleaned file: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the cleaned dataset.",
        ) from exc

    dataset.cleaned_file_path = cleaned_path
    dataset.is_cleaned = True
    dataset.row_count = int(cleaned_df.shape[0])
    dataset.column_count = int(cleaned_df.shape[1])

    try:
        db.commit()
        db.refresh(dataset)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to update dataset record after cleaning: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cleaned the file but could not update the database record.",
        ) from exc

    logger.info("User %s cleaned dataset %s", current_user.id, dataset_id)

    return {
        "dataset_id": dataset.id,
        "is_cleaned": True,
        "report": report,
    }


@router.get("/{dataset_id}/overview")
def dataset_overview_route(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Runs the overview analysis on the dataset. Uses the cleaned file if one
    exists, otherwise falls back to the original upload.
    """
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

    return {
        "dataset_id": dataset.id,
        "used_cleaned_version": active_path == getattr(dataset, "cleaned_file_path", None),
        "overview": overview,
    }
