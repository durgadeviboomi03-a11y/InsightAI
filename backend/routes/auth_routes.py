"""
backend/routes/auth_routes.py

Authentication endpoints:
- POST /register  — create a new user account
- POST /login      — authenticate and receive access/refresh tokens
- POST /refresh     — exchange a valid refresh token for a new access token
- GET  /me          — return the currently authenticated user's profile
"""

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from loguru import logger
from sqlalchemy.orm import Session

from backend.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.database import get_db
from backend.models import User
from backend.schemas import Token, UserCreate, UserLogin, UserResponse

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    """
    Registers a new user account.

    Raises:
        400 Bad Request if the email is already registered.
    """
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    new_user = User(
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    logger.info(f"New user registered: {new_user.email}")
    return new_user


@router.post("/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    """
    Authenticates a user with email + password and returns access/refresh tokens.

    Raises:
        401 Unauthorized if credentials are invalid.
        403 Forbidden if the account has been deactivated.
    """
    user = db.query(User).filter(User.email == payload.email).first()

    if user is None or not verify_password(payload.password, user.hashed_password):
        logger.warning(f"Failed login attempt for email: {payload.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)

    logger.info(f"User logged in: {user.email}")
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
def refresh_access_token(refresh_token: str, db: Session = Depends(get_db)) -> Token:
    """
    Exchanges a valid refresh token for a brand new access + refresh token pair.

    Raises:
        401 Unauthorized if the refresh token is invalid, expired, or the
        user it refers to no longer exists / is inactive.
    """
    try:
        payload = decode_token(refresh_token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        ) from exc

    user = db.query(User).filter(User.public_id == payload.sub).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
        )

    new_access_token = create_access_token(user)
    new_refresh_token = create_refresh_token(user)

    return Token(access_token=new_access_token, refresh_token=new_refresh_token)


@router.get("/me", response_model=UserResponse)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    """Returns the profile of the currently authenticated user."""
    return current_user