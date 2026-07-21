"""
backend/models.py

SQLAlchemy ORM models for InsightAI.

Defines the database schema as Python classes:
- User: application accounts with role-based access
- Dataset: uploaded files and their metadata
- Report: generated PDF/Excel reports linked to a dataset
- ChatHistory: AI chat conversation logs per dataset
- QueryHistory: natural-language-to-SQL query logs
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def _utcnow() -> datetime:
    """Returns the current UTC time. Used as a default for timestamp columns."""
    return datetime.now(timezone.utc)


def _generate_uuid() -> str:
    """Generates a UUID4 string, used for public-facing identifiers."""
    return str(uuid.uuid4())


class UserRole(str, enum.Enum):
    """Role-based access control levels."""
    ADMIN = "admin"
    USER = "user"


class DatasetStatus(str, enum.Enum):
    """Lifecycle status of an uploaded dataset."""
    UPLOADED = "uploaded"
    CLEANING = "cleaning"
    READY = "ready"
    FAILED = "failed"


class ReportFormat(str, enum.Enum):
    """Supported export formats for generated reports."""
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"


class User(Base):
    """Represents an application user (admin or standard user)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=_generate_uuid)

    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # ---------- Relationships ----------
    datasets: Mapped[list["Dataset"]] = relationship(
        "Dataset", back_populates="owner", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


class Dataset(Base):
    """Represents an uploaded dataset (CSV/Excel) and its metadata."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=_generate_uuid)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[DatasetStatus] = mapped_column(
        Enum(DatasetStatus), default=DatasetStatus.UPLOADED, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # ---------- Relationships ----------
    owner: Mapped["User"] = relationship("User", back_populates="datasets")
    reports: Mapped[list["Report"]] = relationship(
        "Report", back_populates="dataset", cascade="all, delete-orphan"
    )
    chat_messages: Mapped[list["ChatHistory"]] = relationship(
        "ChatHistory", back_populates="dataset", cascade="all, delete-orphan"
    )
    queries: Mapped[list["QueryHistory"]] = relationship(
        "QueryHistory", back_populates="dataset", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Dataset id={self.id} filename={self.original_filename} status={self.status}>"


class Report(Base):
    """Represents a generated report (PDF/Excel/CSV) tied to a dataset."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, default=_generate_uuid)

    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[ReportFormat] = mapped_column(Enum(ReportFormat), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # ---------- Relationships ----------
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="reports")

    def __repr__(self) -> str:
        return f"<Report id={self.id} title={self.title} format={self.format}>"


class ChatHistory(Base):
    """Represents a single message in an AI chat conversation about a dataset."""

    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)

    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" or "assistant"
    message: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # ---------- Relationships ----------
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="chat_messages")

    def __repr__(self) -> str:
        return f"<ChatHistory id={self.id} role={self.role}>"


class QueryHistory(Base):
    """Represents a natural-language-to-SQL query and its generated SQL."""

    __tablename__ = "query_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)

    natural_language_query: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str] = mapped_column(Text, nullable=False)
    was_successful: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    # ---------- Relationships ----------
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="queries")

    def __repr__(self) -> str:
        return f"<QueryHistory id={self.id} query={self.natural_language_query[:30]}>"