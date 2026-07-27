"""
backend/services/data_cleaning.py

Automatic data cleaning utilities for uploaded datasets.

Responsibilities:
- Detect and report missing values
- Fill or drop missing values based on column type
- Strip whitespace from string columns
- Attempt to infer and correct column data types
- Flag numeric outliers using the IQR method
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class CleaningReport:
    """
    Summary of what was changed during cleaning, returned alongside the
    cleaned DataFrame so callers (and eventually the frontend) can show
    the user exactly what was done to their data.
    """

    rows_before: int = 0
    rows_after: int = 0
    columns_cleaned: list[str] = field(default_factory=list)
    missing_values_filled: dict[str, int] = field(default_factory=dict)
    rows_dropped_fully_empty: int = 0
    outliers_flagged: dict[str, int] = field(default_factory=dict)
    type_corrections: dict[str, str] = field(default_factory=dict)


def _strip_whitespace(df: pd.DataFrame) -> pd.DataFrame:
    """Strips leading/trailing whitespace from all string/object columns."""
    for column in df.select_dtypes(include="object").columns:
        df[column] = df[column].astype(str).str.strip()
        # Restore actual NaN for cells that were empty strings after stripping.
        df[column] = df[column].replace({"nan": np.nan, "": np.nan})
    return df


def _infer_and_correct_types(df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    """
    Attempts to convert object columns that actually contain numeric or
    datetime data (but were read as strings) into their proper dtype.
    """
    for column in df.select_dtypes(include="object").columns:
        original_dtype = str(df[column].dtype)

        # Try numeric conversion first.
        numeric_attempt = pd.to_numeric(df[column], errors="coerce")
        non_null_ratio = numeric_attempt.notna().sum() / max(len(df), 1)
        if non_null_ratio > 0.9:  # If over 90% of values convert cleanly, treat as numeric.
            df[column] = numeric_attempt
            report.type_corrections[column] = f"{original_dtype} -> numeric"
            continue

        # Try datetime conversion next.
        try:
            datetime_attempt = pd.to_datetime(df[column], errors="coerce")
            non_null_ratio = datetime_attempt.notna().sum() / max(len(df), 1)
            if non_null_ratio > 0.9:
                df[column] = datetime_attempt
                report.type_corrections[column] = f"{original_dtype} -> datetime"
        except (ValueError, TypeError):
            pass  # Column genuinely isn't datetime-like; leave as-is.

    return df


def _fill_missing_values(df: pd.DataFrame, report: CleaningReport) -> pd.DataFrame:
    """
    Fills missing values based on column type:
    - Numeric columns: filled with the median (robust to outliers)
    - Categorical/text columns: filled with the mode (most frequent value)
    - Datetime columns: left as-is (forward-filling dates can be misleading)
    """
    for column in df.columns:
        missing_count = int(df[column].isna().sum())
        if missing_count == 0:
            continue

        if pd.api.types.is_numeric_dtype(df[column]):
            median_value = df[column].median()
            df[column] = df[column].fillna(median_value)
            report.missing_values_filled[column] = missing_count
            report.columns_cleaned.append(column)

        elif pd.api.types.is_datetime64_any_dtype(df[column]):
            # Intentionally not auto-filled — a missing date shouldn't be guessed.
            continue

        else:
            mode_series = df[column].mode()
            if not mode_series.empty:
                df[column] = df[column].fillna(mode_series.iloc[0])
                report.missing_values_filled[column] = missing_count
                report.columns_cleaned.append(column)

    return df


def _flag_outliers(df: pd.DataFrame, report: CleaningReport) -> None:
    """
    Flags (but does not remove) numeric outliers using the IQR method.
    Outliers are often meaningful data points, not errors, so we report
    their count per column rather than silently dropping them.
    """
    for column in df.select_dtypes(include="number").columns:
        q1 = df[column].quantile(0.25)
        q3 = df[column].quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        outlier_count = int(((df[column] < lower_bound) | (df[column] > upper_bound)).sum())
        if outlier_count > 0:
            report.outliers_flagged[column] = outlier_count


def clean_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """
    Runs the full automatic cleaning pipeline on a DataFrame.

    Steps (in order):
        1. Drop rows that are entirely empty.
        2. Strip whitespace from string columns.
        3. Infer and correct column types (numeric/datetime stored as text).
        4. Fill missing values (median for numeric, mode for categorical).
        5. Flag (not remove) numeric outliers via IQR.

    Args:
        df: The raw DataFrame as read from the uploaded file.

    Returns:
        A tuple of (cleaned_dataframe, cleaning_report).
    """
    report = CleaningReport(rows_before=len(df))

    # Step 1: Drop fully empty rows.
    rows_before_dropna = len(df)
    df = df.dropna(how="all").reset_index(drop=True)
    report.rows_dropped_fully_empty = rows_before_dropna - len(df)

    # Step 2: Strip whitespace.
    df = _strip_whitespace(df)

    # Step 3: Infer/correct types.
    df = _infer_and_correct_types(df, report)

    # Step 4: Fill missing values.
    df = _fill_missing_values(df, report)

    # Step 5: Flag outliers.
    _flag_outliers(df, report)

    report.rows_after = len(df)

    logger.info(
        f"Cleaning complete: {report.rows_before} -> {report.rows_after} rows, "
        f"{len(report.columns_cleaned)} columns had missing values filled, "
        f"{len(report.type_corrections)} columns had type corrections."
    )

    return df, report