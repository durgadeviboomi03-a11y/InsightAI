"""
backend/routes/user_routes.py

User profile endpoints:
- GET   /users/me        — get the current user's own profile (duplicate of /auth/me for REST consistency)
- PATCH /users/me        — update the current user's own profile (full_name and/or email)
- GET   /users           — (admin only) list all registered users
- PATCH /users/{public_id}/deactivate — (admin only) deactivate a user account
"""

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy.orm import Session

from backend.auth import get_current_user, require_admin
from backend.database import get_db
from backend.models import User
from backend.schemas import MessageResponse, UserResponse, UserUpdate

router = APIRouter()


@router.get("/me", response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_user)) -> User:
    """Returns the currently authenticated user's profile."""
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_my_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """
    Updates the current user's own profile.

    Only fields explicitly provided in the request body are changed
    (partial update), thanks to `exclude_unset=True`.

    Raises:
        400 Bad Request if the new email is already taken by another account.
    """
    update_data = payload.model_dump(exclude_unset=True)

    if "email" in update_data and update_data["email"] != current_user.email:
        existing = db.query(User).filter(User.email == update_data["email"]).first()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That email is already in use by another account.",
            )

    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)

    logger.info(f"User updated profile: {current_user.email}")
    return current_user


@router.get("", response_model=list[UserResponse])
def list_all_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[User]:
    """
    (Admin only) Lists all registered users in the system.
    """
    return db.query(User).order_by(User.created_at.desc()).all()


@router.patch("/{public_id}/deactivate", response_model=MessageResponse)
def deactivate_user(
    public_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MessageResponse:
    """
    (Admin only) Deactivates a user account by public_id.

    Deactivated users can no longer log in or use existing tokens
    (enforced by get_current_user's is_active check).

    Raises:
        404 Not Found if no user with that public_id exists.
        400 Bad Request if an admin tries to deactivate their own account.
    """
    target_user = db.query(User).filter(User.public_id == public_id).first()
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    if target_user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account.",
        )

    target_user.is_active = False
    db.commit()

    logger.info(f"Admin {current_user.email} deactivated user {target_user.email}")
    return MessageResponse(detail=f"User {target_user.email} has been deactivated.")