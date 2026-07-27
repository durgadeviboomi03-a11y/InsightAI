"""
backend/services/ai_chat.py

AI chat service — lets users ask natural-language questions about a
dataset and get context-aware answers via the Gemini API.

The approach: rather than sending the entire dataset to the AI (expensive,
often exceeds context limits, and unnecessary), we build a compact "data
profile" — schema, dtypes, summary stats, and a small sample of rows —
and include that as context alongside the user's question.
"""

import google.generativeai as genai
import pandas as pd
from loguru import logger

from backend.config import get_settings

settings = get_settings()

_model = None  # Lazily initialized on first use.


def _get_model() -> genai.GenerativeModel:
    """
    Lazily configures and returns the Gemini model client.

    Lazy initialization avoids configuring the API key at import time
    (useful for tests/environments where GEMINI_API_KEY isn't set yet),
    and avoids re-configuring on every single call.
    """
    global _model
    if _model is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to your .env file to use AI chat."
            )
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _model = genai.GenerativeModel(settings.GEMINI_MODEL)
    return _model


def _build_dataset_profile(df: pd.DataFrame, sample_rows: int = 5) -> str:
    """
    Builds a compact text summary of a DataFrame's structure, suitable
    for including in an AI prompt without sending the entire dataset.

    Includes: shape, column names/dtypes, basic numeric stats, and a
    small sample of actual rows (so the AI can see real data patterns).
    """
    lines: list[str] = []

    lines.append(f"Dataset shape: {len(df)} rows, {len(df.columns)} columns.")
    lines.append("\nColumns and types:")
    for column, dtype in df.dtypes.items():
        lines.append(f"  - {column} ({dtype})")

    numeric_df = df.select_dtypes(include="number")
    if not numeric_df.empty:
        lines.append("\nNumeric column summary:")
        for column in numeric_df.columns:
            series = numeric_df[column].dropna()
            if series.empty:
                continue
            lines.append(
                f"  - {column}: mean={series.mean():.2f}, min={series.min():.2f}, max={series.max():.2f}"
            )

    lines.append(f"\nSample rows (first {sample_rows}):")
    lines.append(df.head(sample_rows).to_string(index=False))

    return "\n".join(lines)


def ask_ai_about_dataset(question: str, dataframe: pd.DataFrame) -> str:
    """
    Sends a natural-language question about a dataset to the Gemini API
    and returns the AI's plain-text answer.

    Args:
        question: The user's plain-English question.
        dataframe: The dataset to answer questions about.

    Returns:
        The AI's response as a plain-text string.

    Raises:
        RuntimeError: if GEMINI_API_KEY isn't configured.
        Exception: propagates any Gemini API errors (network issues,
        rate limits, invalid key) to the caller, which is expected to
        convert it into a proper HTTP error (see chat_routes.py).
    """
    model = _get_model()
    dataset_profile = _build_dataset_profile(dataframe)

    prompt = f"""You are a helpful data analyst assistant. A user has uploaded a dataset
and is asking you a question about it. Use the dataset profile below to answer
accurately. If the question can't be answered from the given information, say so
clearly rather than guessing.

DATASET PROFILE:
{dataset_profile}

USER QUESTION:
{question}

Provide a clear, concise, and accurate answer based only on the dataset profile above."""

    logger.info(f"Sending AI chat request (question length: {len(question)} chars)")
    response = model.generate_content(prompt)

    if not response.text:
        raise RuntimeError("The AI service returned an empty response.")

    return response.text.strip()