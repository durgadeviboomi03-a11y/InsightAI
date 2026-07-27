"""
backend/services/forecasting.py

Time-series forecasting service.

Uses linear regression on a numeric time index (a lightweight, dependency-
minimal approach) to project future values, with confidence bounds derived
from the residual standard error. Suitable for datasets with a general
trend; not intended to model complex seasonality.
"""

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


def generate_forecast(
    dataframe: pd.DataFrame,
    date_column: str,
    value_column: str,
    periods_ahead: int = 30,
) -> tuple[list[str], list[float], list[float], list[float]]:
    """
    Generates a forecast for `value_column`, ordered by `date_column`.

    Approach:
        1. Parse and sort by the date column.
        2. Fit a linear regression on (time index -> value).
        3. Predict `periods_ahead` future points beyond the last known date.
        4. Compute a 95% confidence interval band using residual std error.

    Args:
        dataframe: The source DataFrame.
        date_column: Name of the column containing dates.
        value_column: Name of the numeric column to forecast.
        periods_ahead: How many future periods to predict.

    Returns:
        A tuple of (dates, predicted_values, confidence_lower, confidence_upper),
        where dates includes only the future predicted dates (not historical).

    Raises:
        ValueError: if the date column can't be parsed, or there isn't
        enough valid data to fit a model.
    """
    df = dataframe[[date_column, value_column]].dropna().copy()

    df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
    df = df.dropna(subset=[date_column])

    if len(df) < 3:
        raise ValueError(
            f"Not enough valid data points to forecast (found {len(df)}, need at least 3)."
        )

    df = df.sort_values(by=date_column).reset_index(drop=True)

    # Infer the typical gap between consecutive dates, to project future
    # dates at a consistent interval (e.g. daily, weekly, monthly).
    date_diffs = df[date_column].diff().dropna()
    typical_interval = date_diffs.median()
    if pd.isna(typical_interval) or typical_interval.total_seconds() <= 0:
        typical_interval = pd.Timedelta(days=1)

    # Use a simple integer time index as the regression feature.
    time_index = np.arange(len(df)).reshape(-1, 1)
    values = df[value_column].values

    model = LinearRegression()
    model.fit(time_index, values)

    # ---------- Predict future points ----------
    future_index = np.arange(len(df), len(df) + periods_ahead).reshape(-1, 1)
    predicted_values = model.predict(future_index)

    # ---------- Confidence interval via residual standard error ----------
    fitted_values = model.predict(time_index)
    residuals = values - fitted_values
    residual_std = float(np.std(residuals)) if len(residuals) > 1 else 0.0

    # Approximate 95% confidence band (±1.96 standard errors).
    margin = 1.96 * residual_std
    confidence_lower = (predicted_values - margin).tolist()
    confidence_upper = (predicted_values + margin).tolist()

    # ---------- Generate future dates ----------
    last_date = df[date_column].iloc[-1]
    future_dates = [
        (last_date + typical_interval * (i + 1)).strftime("%Y-%m-%d")
        for i in range(periods_ahead)
    ]

    return future_dates, predicted_values.tolist(), confidence_lower, confidence_upper