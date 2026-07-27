"""
backend/routes/admin_routes.py

Admin dashboard endpoints:
- GET /admin/stats          — platform-wide usage statistics
- GET /admin/datasets       — list all datasets across all users
- GET /admin/reports        — list all reports across all users
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.auth import require_admin
from backend.database import get_db
from backend.models import ChatHistory, Dataset, DatasetStatus, QueryHistory, Report, User, UserRole
from backend.schemas import DatasetResponse, ReportResponse

router = APIRouter()


@router.get("/stats")
def get_platform_stats(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """
    (Admin only) Returns aggregate platform-wide statistics: total users,
    active users, admins, datasets by status, total reports, chat messages,
    and NL→SQL queries.
    """
    total_users = db.query(func.count(User.id)).scalar()
    active_users = db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar()
    total_admins = db.query(func.count(User.id)).filter(User.role == UserRole.ADMIN).scalar()

    total_datasets = db.query(func.count(Dataset.id)).scalar()
    datasets_ready = db.query(func.count(Dataset.id)).filter(Dataset.status == DatasetStatus.READY).scalar()
    datasets_failed = db.query(func.count(Dataset.id)).filter(Dataset.status == DatasetStatus.FAILED).scalar()

    total_reports = db.query(func.count(Report.id)).scalar()
    total_chat_messages = db.query(func.count(ChatHistory.id)).scalar()
    total_queries = db.query(func.count(QueryHistory.id)).scalar()

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "inactive": total_users - active_users,
            "admins": total_admins,
        },
        "datasets": {
            "total": total_datasets,
            "ready": datasets_ready,
            "failed": datasets_failed,
        },
        "reports": {
            "total": total_reports,
        },
        "ai_usage": {
            "chat_messages": total_chat_messages,
            "nl_queries": total_queries,
        },
    }


@router.get("/datasets", response_model=list[DatasetResponse])
def list_all_datasets(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Dataset]:
    """(Admin only) Lists all datasets across every user, most recent first."""
    return db.query(Dataset).order_by(Dataset.uploaded_at.desc()).all()


@router.get("/reports", response_model=list[ReportResponse])
def list_all_reports(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Report]:
    """(Admin only) Lists all generated reports across every user, most recent first."""
    return db.query(Report).order_by(Report.created_at.desc()).all()