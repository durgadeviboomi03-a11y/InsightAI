"""
backend/schemas.py

Pydantic schemas for request validation and response serialization.

Kept separate from backend/models.py (the ORM layer) so that:
- Sensitive fields (e.g. hashed_password) are never exposed in API responses
- Input validation rules (e.g. password length) live independently of storage
- API contracts can evolve without changing the database schema directly
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.models import DatasetStatus, ReportFormat, UserRole


# =========================================================
# ---------------------- User Schemas ----------------------
# =========================================================

class UserCreate(BaseModel):
    """Schema for user registration requests."""

    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    """Schema for user login requests."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Schema for returning user data in API responses. Never includes password."""

    model_config = ConfigDict(from_attributes=True)

    public_id: str
    full_name: str
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    """Schema for updating a user's own profile."""

    full_name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    email: Optional[EmailStr] = None


# =========================================================
# --------------------- Token Schemas ----------------------
# =========================================================

class Token(BaseModel):
    """Schema returned after successful login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Schema representing the decoded contents of a JWT payload."""

    sub: str  # subject — typically the user's public_id
    exp: int
    role: UserRole


# =========================================================
# -------------------- Dataset Schemas ---------------------
# =========================================================

class DatasetResponse(BaseModel):
    """Schema for returning dataset metadata in API responses."""

    model_config = ConfigDict(from_attributes=True)

    public_id: str
    original_filename: str
    file_size_bytes: int
    row_count: Optional[int]
    column_count: Optional[int]
    status: DatasetStatus
    error_message: Optional[str]
    uploaded_at: datetime


class DatasetOverview(BaseModel):
    """Schema for the automatic profiling summary generated after upload."""

    row_count: int
    column_count: int
    column_names: list[str]
    column_types: dict[str, str]
    missing_values: dict[str, int]
    numeric_summary: dict[str, dict[str, float]]


# =========================================================
# --------------------- Report Schemas ----------------------
# =========================================================

class ReportCreateRequest(BaseModel):
    """Schema for requesting a new report to be generated."""

    dataset_public_id: str
    title: str = Field(min_length=1, max_length=255)
    format: ReportFormat


class ReportResponse(BaseModel):
    """Schema for returning report metadata in API responses."""

    model_config = ConfigDict(from_attributes=True)

    public_id: str
    title: str
    format: ReportFormat
    created_at: datetime


# =========================================================
# ----------------- AI Chat / NL→SQL Schemas -----------------
# =========================================================

class ChatMessageRequest(BaseModel):
    """Schema for sending a message to the AI chat about a dataset."""

    dataset_public_id: str
    message: str = Field(min_length=1, max_length=2000)


class ChatMessageResponse(BaseModel):
    """Schema for a single AI chat message in the response."""

    model_config = ConfigDict(from_attributes=True)

    role: str
    message: str
    created_at: datetime


class NLQueryRequest(BaseModel):
    """Schema for a natural-language-to-SQL query request."""

    dataset_public_id: str
    question: str = Field(min_length=1, max_length=1000)


class NLQueryResponse(BaseModel):
    """Schema for the result of a natural-language-to-SQL query."""

    generated_sql: str
    result_preview: list[dict]
    row_count: int


# =========================================================
# -------------------- Forecast Schemas ----------------------
# =========================================================

class ForecastRequest(BaseModel):
    """Schema for requesting a time-series forecast."""

    dataset_public_id: str
    date_column: str
    value_column: str
    periods_ahead: int = Field(default=30, ge=1, le=365)


class ForecastResponse(BaseModel):
    """Schema for returning forecast results."""

    dates: list[str]
    predicted_values: list[float]
    confidence_lower: list[float]
    confidence_upper: list[float]


# =========================================================
# ------------------- Generic API Schemas --------------------
# =========================================================

class MessageResponse(BaseModel):
    """Generic schema for simple success/status messages."""

    detail: str