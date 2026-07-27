"""
backend/services/sql_generator.py

Natural-language-to-SQL service.

Approach:
1. Load the dataset into a temporary in-memory SQLite database (table
   name always "data"), so we get real, standard SQL semantics.
2. Ask Gemini to translate the user's plain-English question into a SQL
   query against that exact schema.
3. Validate the generated SQL is read-only (SELECT only) before running it,
   to prevent any destructive or unexpected statements.
4. Execute the query against the in-memory SQLite table and return results.
"""

import re
import sqlite3

import google.generativeai as genai
import pandas as pd
from loguru import logger

from backend.config import get_settings

settings = get_settings()

_model = None  # Lazily initialized on first use.

# Only these statement types are ever allowed to execute.
_ALLOWED_SQL_PREFIX = re.compile(r"^\s*SELECT\b", re.IGNORECASE)

# Any of these keywords appearing anywhere in the generated SQL causes an
# immediate rejection, regardless of where they appear in the statement.
_FORBIDDEN_KEYWORDS = [
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
    "ATTACH", "PRAGMA", "REPLACE", "TRUNCATE", "GRANT", "REVOKE",
]


def _get_model() -> genai.GenerativeModel:
    """Lazily configures and returns the Gemini model client."""
    global _model
    if _model is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to your .env file to use NL-to-SQL."
            )
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _model = genai.GenerativeModel(settings.GEMINI_MODEL)
    return _model


def _build_schema_description(df: pd.DataFrame) -> str:
    """Builds a compact text description of the DataFrame's schema for the AI prompt."""
    lines = ["Table name: data", "Columns:"]
    for column, dtype in df.dtypes.items():
        sql_type = "REAL" if pd.api.types.is_numeric_dtype(dtype) else "TEXT"
        lines.append(f"  - {column} ({sql_type})")
    return "\n".join(lines)


def _extract_sql_from_response(raw_text: str) -> str:
    """
    Extracts a clean SQL statement from the AI's raw response text,
    stripping markdown code fences if present (e.g. ```sql ... ```).
    """
    text = raw_text.strip()
    fenced_match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        text = fenced_match.group(1).strip()
    return text.rstrip(";").strip()


def _validate_sql_is_safe(sql: str) -> None:
    """
    Validates that a generated SQL statement is read-only and safe to run.

    Raises:
        ValueError: if the statement isn't a SELECT, or contains any
        forbidden keyword anywhere in the text.
    """
    if not _ALLOWED_SQL_PREFIX.match(sql):
        raise ValueError("Generated query must be a SELECT statement.")

    upper_sql = sql.upper()
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper_sql):
            raise ValueError(f"Generated query contains a forbidden keyword: {keyword}")


def _generate_sql_from_question(question: str, df: pd.DataFrame) -> str:
    """Uses Gemini to translate a natural-language question into a SQL SELECT statement."""
    model = _get_model()
    schema_description = _build_schema_description(df)

    prompt = f"""You are a SQL generation assistant. Given a table schema and a question,
write a single valid SQLite SELECT query that answers the question.

RULES:
- Only generate SELECT statements. Never generate INSERT, UPDATE, DELETE, DROP, ALTER, or any other modifying statement.
- Only use the table and columns described below. Do not invent column names.
- Return ONLY the SQL query, with no explanation, no markdown formatting, and no semicolon at the end.

{schema_description}

QUESTION:
{question}

SQL QUERY:"""

    response = model.generate_content(prompt)
    if not response.text:
        raise RuntimeError("The AI service returned an empty response while generating SQL.")

    return _extract_sql_from_response(response.text)


def generate_and_run_sql(question: str, dataframe: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    """
    Converts a natural-language question into SQL, validates it's safe,
    executes it against the dataset, and returns both the query and results.

    Args:
        question: The user's plain-English question.
        dataframe: The dataset to query.

    Returns:
        A tuple of (generated_sql, result_dataframe).

    Raises:
        RuntimeError: if GEMINI_API_KEY isn't configured, or the AI
        returns an empty response.
        ValueError: if the generated SQL fails safety validation.
        sqlite3.Error: if the generated SQL is invalid or fails to execute
        against the actual data (e.g. references a non-existent column).
    """
    generated_sql = _generate_sql_from_question(question, dataframe)
    _validate_sql_is_safe(generated_sql)

    # Load the dataset into a fresh, temporary in-memory SQLite database.
    # Using an in-memory DB (not the app's real database) keeps this
    # completely isolated — no risk to actual application data, and no
    # persistence needed since the "table" only needs to exist for this query.
    connection = sqlite3.connect(":memory:")
    try:
        dataframe.to_sql("data", connection, index=False, if_exists="replace")
        result_df = pd.read_sql_query(generated_sql, connection)
    finally:
        connection.close()

    logger.info(f"NL→SQL query executed successfully. SQL: {generated_sql}")
    return generated_sql, result_df