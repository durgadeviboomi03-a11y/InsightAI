"""
backend/routes/chat_routes.py

Exposes AI chat-with-dataset as an API endpoint:

    POST  /datasets/{id}/chat          -> send a message, get a reply
    GET   /datasets/{id}/chat/history  -> fetch stored conversation history
    DELETE /datasets/{id}/chat/history -> clear conversation history

Conversation history is persisted in a ChatMessage table so it survives
across requests/page reloads, rather than being held only in memory.
"""

import os
import json
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Session

from backend.database import get_db, Base
from backend.auth import get_current_user
from backend.models import User
from backend.routes.dataset_routes import _get_owned_dataset_or_404, _read_dataframe
from backend.routes.cleaning_routes import _active_file_path
from backend.services.data_analysis import analyze_dataset
from backend.services.ai_chat import ask_dataset_question

logger = logging.getLogger("insightai.chat_routes")

router = APIRouter(prefix="/datasets", tags=["AI Chat"])

MAX_STORED_MESSAGES = 40  # per dataset per user, oldest trimmed beyond this


class ChatMessage(Base):
    """A single stored turn (user or assistant) in a dataset's chat history."""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


def _load_history(dataset_id: int, user_id: int, db: Session) -> List[dict]:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.dataset_id == dataset_id, ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in messages]


@router.post("/{dataset_id}/chat")
def chat_with_dataset(
    dataset_id: int,
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sends a message to the AI about this dataset and stores both turns."""
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

    history = _load_history(dataset_id, current_user.id, db)

    try:
        result = ask_dataset_question(
            overview=overview,
            dataset_name=dataset.original_filename,
            user_message=request.message,
            conversation_history=history,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Persist both turns
    db.add(ChatMessage(dataset_id=dataset_id, user_id=current_user.id, role="user", content=request.message))
    db.add(ChatMessage(dataset_id=dataset_id, user_id=current_user.id, role="assistant", content=result["reply"]))
    db.commit()

    # Trim old messages beyond MAX_STORED_MESSAGES for this dataset/user
    all_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.dataset_id == dataset_id, ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    if len(all_messages) > MAX_STORED_MESSAGES:
        for old_message in all_messages[: len(all_messages) - MAX_STORED_MESSAGES]:
            db.delete(old_message)
        db.commit()

    logger.info("User %s chatted about dataset %s", current_user.id, dataset_id)

    return {"dataset_id": dataset_id, "reply": result["reply"]}


@router.get("/{dataset_id}/chat/history")
def get_chat_history(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns the stored chat history for this dataset."""
    _get_owned_dataset_or_404(dataset_id, current_user, db)  # ownership check
    return {"dataset_id": dataset_id, "history": _load_history(dataset_id, current_user.id, db)}


@router.delete("/{dataset_id}/chat/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_chat_history(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deletes all stored chat history for this dataset (for this user)."""
    _get_owned_dataset_or_404(dataset_id, current_user, db)  # ownership check
    db.query(ChatMessage).filter(
        ChatMessage.dataset_id == dataset_id, ChatMessage.user_id == current_user.id
    ).delete()
    db.commit()
    return None
