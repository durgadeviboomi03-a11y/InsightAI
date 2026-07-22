"""
backend/auth.py

Authentication utilities for InsightAI:
- Password hashing and verification (bcrypt via passlib)
- JWT access/refresh token creation and decoding (python-jose)
- FastAPI dependency for extracting and validating the current user from a token
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from loguru import logger
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database import get_db
from backend.models import User, UserRole
from backend.schemas import TokenPayload

settings = get_settings()

# ---------- Password Hashing ----------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------- OAuth2 Scheme ----------
# tokenUrl points to the login endpoint that issues tokens (used by Swagger UI's "Authorize" button).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(plain_password: str) -> str:
    """Hashes a plain-text password using bcrypt. Never store plain passwords."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain-text password against a stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(subject: str, role: UserRole, expires_delta: timedelta) -> str:
    """
    Internal helper that builds and signs a JWT.

    Args:
        subject: The user's public_id, embedded as the token's `sub` claim.
        role: The user's role, embedded so route dependencies can check
              permissions without an extra database lookup.
        expires_delta: How long the token remains valid.
    """
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode: dict[str, Any] = {
        "sub": subject,
        "role": role.value,
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user: User) -> str:
    """Creates a short-lived access token for API authentication."""
    return _create_token(
        subject=user.public_id,
        role=user.role,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user: User) -> str:
    """Creates a long-lived refresh token used to obtain new access tokens."""
    return _create_token(
        subject=user.public_id,
        role=user.role,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> TokenPayload:
    """
    Decodes and validates a JWT, raising an HTTPException if it's invalid,
    malformed, or expired.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return TokenPayload(**payload)
    except JWTError as exc:
        logger.warning(f"JWT decode failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency that extracts the current authenticated user from
    the request's Bearer token.

    Usage in a route:
        @router.get("/me")
        def me(current_user: User = Depends(get_current_user)):
            ...
    """
    payload = decode_token(token)

    user = db.query(User).filter(User.public_id == payload.sub).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    FastAPI dependency that restricts a route to admin users only.

    Usage in a route:
        @router.get("/admin-only")
        def admin_stuff(current_user: User = Depends(require_admin)):
            ...
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user