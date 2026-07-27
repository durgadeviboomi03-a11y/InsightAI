"""
backend/services/anomaly_detection.py

Multivariate anomaly detection using Isolation Forest.

Unlike the per-column IQR outlier flagging in data_cleaning.py (which looks
at one column at a time), this considers all numeric columns together —
catching rows that are unusual as a *combination* of values, even if no
single value looks extreme on its own.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler


@dataclass
class AnomalyResult:
    """Container for anomaly detection outputs."""

    total_rows_checked: int = 0
    anomaly_count: int = 0
    anomaly_indices: list[int] = field(default_factory=list)
    anomaly_rows: list[dict] = field(default_factory=list)
    columns_used: list[str] = field(default_factory=list)


def detect_anomalies(
    df: pd.DataFrame,
    contamination: float = 0.05,
    max_rows_to_return: int = 50,
    random_state: int = 42,
) -> AnomalyResult:
    """
    Detects anomalous rows using Isolation Forest on all numeric columns.

    Args:
        df: The (ideally already-cleaned) DataFrame to analyze.
        contamination: Expected proportion of anomalies in the data
            (0.05 = assume roughly 5% of rows are anomalous). This is an
            estimate, not an exact count — Isolation Forest uses it to
            calibrate its decision threshold.
        max_rows_to_return: Caps how many anomalous rows are returned in
            full (to avoid a huge payload if a dataset is very noisy).
        random_state: Fixed seed for reproducible results across runs.

    Returns:
        An AnomalyResult with the count, indices, and sample rows of
        detected anomalies.

    Raises:
        ValueError: if there are fewer than 2 numeric columns (Isolation
        Forest needs at least some multivariate structure to be meaningful)
        or fewer than 10 rows (too little data to detect meaningful outliers).
    """
    numeric_df = df.select_dtypes(include="number").dropna()

    if numeric_df.shape[1] < 1:
        raise ValueError("Dataset has no numeric columns to analyze for anomalies.")
    if len(numeric_df) < 10:
        raise ValueError(
            f"Not enough rows to detect anomalies reliably (found {len(numeric_df)}, need at least 10)."
        )

    # Scale features so columns with larger numeric ranges (e.g. "revenue"
    # in the thousands) don't dominate columns with smaller ranges
    # (e.g. "rating" from 1-5) purely due to scale.
    scaler = StandardScaler()
    scaled_values = scaler.fit_transform(numeric_df)

    model = IsolationForest(contamination=contamination, random_state=random_state)
    predictions = model.fit_predict(scaled_values)  # -1 = anomaly, 1 = normal

    anomaly_mask = predictions == -1
    anomaly_indices = numeric_df.index[anomaly_mask].tolist()

    # Pull the original (unscaled, full-column) rows for readability in the response.
    anomaly_rows_df = df.loc[anomaly_indices].head(max_rows_to_return)
    anomaly_rows = anomaly_rows_df.reset_index().rename(columns={"index": "original_row_index"}).to_dict(
        orient="records"
    )

    logger.info(
        f"Anomaly detection complete: {len(anomaly_indices)} anomalies found "
        f"out of {len(numeric_df)} rows checked."
    )

    return AnomalyResult(
        total_rows_checked=len(numeric_df),
        anomaly_count=len(anomaly_indices),
        anomaly_indices=anomaly_indices,
        anomaly_rows=anomaly_rows,
        columns_used=numeric_df.columns.tolist(),
    )