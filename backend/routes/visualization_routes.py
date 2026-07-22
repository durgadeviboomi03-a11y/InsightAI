"""
backend/routes/visualization_routes.py

Exposes automatic chart generation as an API endpoint:

    GET /datasets/{id}/charts -> runs generate_visualizations() on the
                                 dataset's active file and returns chart specs

Reuses the ownership check, active-file resolution, and file-reading helpers
already defined in dataset_routes.py / cleaning_routes.py rather than
duplicating them.
"""

import os
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.auth import get_current_user
from backend.models import User
from backend.routes.dataset_routes import Dataset, _get_owned_dataset_or_404, _read_dataframe
from backend.routes.cleaning_routes import _active_file_path
from backend.services.visualization import generate_visualizations

logger = logging.getLogger("insightai.visualization_routes")

router = APIRouter(prefix="/datasets", tags=["Visualization"])


@router.get("/{dataset_id}/charts")
def get_dataset_charts(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns an auto-generated set of chart specs for the dataset, using the
    cleaned version if one exists, otherwise the original upload.
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
        result = generate_visualizations(df)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    logger.info("Generated %s charts for dataset %s (user %s)",
                result["chart_count"], dataset_id, current_user.id)

    return {
        "dataset_id": dataset.id,
        "used_cleaned_version": active_path == getattr(dataset, "cleaned_file_path", None),
        **result,
    }
