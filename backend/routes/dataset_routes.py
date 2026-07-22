"""
backend/routes/dataset_routes.py

Dataset upload, listing, retrieval, and deletion endpoints for InsightAI.

These routes let an authenticated user:
    - Upload a CSV or Excel file
    - List all datasets they have uploaded
    - Fetch metadata / a preview for a specific dataset
    - Delete a dataset (and its file from disk)

This file assumes the following already exist in your project:
    - backend/database.py  -> get_db() dependency (SQLAlchemy Session)
    - backend/auth.py      -> get_current_user() dependency (returns User)
    - backend/models.py    -> User model with an integer primary key `id`

The `Dataset` model below is defined in this file for completeness. If you
already have (or want) a central models.py, move the class there and just
import it here instead.
"""

import os
import uuid
import logging
from datetime import datetime
from typing import List

import pandas as pd
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import Session, relationship

from backend.database import get_db, Base
from backend.auth import get_current_user
from backend.models import User
from backend.schemas import DatasetOut, DatasetPreview

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
logger = logging.getLogger("insightai.dataset_routes")
logging.basicConfig(level=logging.INFO)

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))

os.makedirs(UPLOAD_DIR, exist_ok=True)

router = APIRouter(prefix="/datasets", tags=["Datasets"])


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
class Dataset(Base):
    """
    Represents a single uploaded dataset belonging to a user.

    NOTE: If you already have a Dataset model in backend/models.py, delete
    this class and `from backend.models import Dataset` instead — SQLAlchemy
    will raise a mapper error if the same table is declared twice.
    """

    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True)
    file_path = Column(String(500), nullable=False)
    file_size_kb = Column(Integer, nullable=False)
    row_count = Column(Integer, nullable=True)
    column_count = Column(Integer, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    owner = relationship("User", backref="datasets")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _validate_extension(filename: str) -> str:
    """Returns the lowercase extension if allowed, else raises 400."""
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}",
        )
    return ext


def _read_dataframe(file_path: str, ext: str) -> pd.DataFrame:
    """Loads a CSV or Excel file into a pandas DataFrame with error handling."""
    try:
        if ext == ".csv":
            return pd.read_csv(file_path)
        return pd.read_excel(file_path)
    except Exception as exc:
        logger.error("Failed to parse uploaded file %s: %s", file_path, exc)
        # Clean up the bad file so it doesn't linger on disk
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not parse the uploaded file. Please check it is a valid CSV/Excel file.",
        ) from exc


def _get_owned_dataset_or_404(dataset_id: int, user: User, db: Session) -> Dataset:
    """Fetches a dataset by id, ensuring it belongs to the current user."""
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    if dataset.user_id != user.id:
        # 404 instead of 403 to avoid leaking existence of other users' data
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")
    return dataset


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@router.post("/upload", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a CSV or Excel file, store it on disk, register it in the
    database, and return basic metadata about it.
    """
    ext = _validate_extension(file.filename)

    # Read the raw bytes once so we can both size-check and write to disk
    contents = await file.read()
    size_kb = len(contents) // 1024

    if size_kb > MAX_FILE_SIZE_MB * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_FILE_SIZE_MB}MB limit.",
        )

    stored_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)

    try:
        with open(file_path, "wb") as f:
            f.write(contents)
    except OSError as exc:
        logger.error("Failed to write uploaded file to disk: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the uploaded file.",
        ) from exc

    df = _read_dataframe(file_path, ext)

    dataset = Dataset(
        user_id=current_user.id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        file_path=file_path,
        file_size_kb=size_kb,
        row_count=int(df.shape[0]),
        column_count=int(df.shape[1]),
    )

    try:
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
    except Exception as exc:
        db.rollback()
        logger.error("Database error saving dataset record: %s", exc)
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not register the dataset in the database.",
        ) from exc

    logger.info("User %s uploaded dataset %s (%s rows, %s cols)",
                current_user.id, dataset.id, dataset.row_count, dataset.column_count)

    return dataset


@router.get("/", response_model=List[DatasetOut])
def list_datasets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns every dataset uploaded by the current user, most recent first."""
    return (
        db.query(Dataset)
        .filter(Dataset.user_id == current_user.id)
        .order_by(Dataset.uploaded_at.desc())
        .all()
    )


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns metadata for a single dataset owned by the current user."""
    return _get_owned_dataset_or_404(dataset_id, current_user, db)


@router.get("/{dataset_id}/preview", response_model=DatasetPreview)
def preview_dataset(
    dataset_id: int,
    rows: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns column names, dtypes, and the first `rows` records of the
    dataset — used by the frontend to render a quick preview table.
    """
    dataset = _get_owned_dataset_or_404(dataset_id, current_user, db)

    if not os.path.exists(dataset.file_path):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="The underlying file is missing from storage.",
        )

    ext = os.path.splitext(dataset.file_path)[1].lower()
    df = _read_dataframe(dataset.file_path, ext)

    rows = max(1, min(rows, 100))  # clamp to a sane range
    preview_df = df.head(rows)

    return {
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "rows": preview_df.where(pd.notnull(preview_df), None).to_dict(orient="records"),
        "total_rows": int(df.shape[0]),
        "total_columns": int(df.shape[1]),
    }


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deletes a dataset record and its file from disk."""
    dataset = _get_owned_dataset_or_404(dataset_id, current_user, db)

    if os.path.exists(dataset.file_path):
        try:
            os.remove(dataset.file_path)
        except OSError as exc:
            logger.warning("Could not remove file %s from disk: %s", dataset.file_path, exc)

    db.delete(dataset)
    db.commit()

    logger.info("User %s deleted dataset %s", current_user.id, dataset_id)
    return None
