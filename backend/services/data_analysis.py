"""
backend/services/data_analysis.py

Statistical analysis and automatic business insight generation.

Responsibilities:
- Compute summary statistics for numeric and categorical columns
- Detect correlations between numeric columns
- Identify simple upward/downward trends in ordered numeric data
- Generate plain-English insight statements summarizing key findings
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class AnalysisResult:
    """Container for all computed analysis outputs."""

    numeric_summary: dict[str, dict[str, float]] = field(default_factory=dict)
    categorical_summary: dict[str, dict[str, int]] = field(default_factory=dict)
    correlations: dict[str, dict[str, float]] = field(default_factory=dict)
    trends: dict[str, str] = field(default_factory=dict)
    insights: list[str] = field(default_factory=list)


def _compute_numeric_summary(df: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Computes mean, median, std, min, max for every numeric column."""
    summary: dict[str, dict[str, float]] = {}
    for column in df.select_dtypes(include="number").columns:
        series = df[column].dropna()
        if series.empty:
            continue
        summary[column] = {
            "mean": float(series.mean()),
            "median": float(series.median()),
            "std": float(series.std()) if len(series) > 1 else 0.0,
            "min": float(series.min()),
            "max": float(series.max()),
        }
    return summary


def _compute_categorical_summary(df: pd.DataFrame, top_n: int = 5) -> dict[str, dict[str, int]]:
    """Computes the top N most frequent values for every categorical/text column."""
    summary: dict[str, dict[str, int]] = {}
    for column in df.select_dtypes(include="object").columns:
        value_counts = df[column].value_counts().head(top_n)
        summary[column] = {str(k): int(v) for k, v in value_counts.items()}
    return summary


def _compute_correlations(df: pd.DataFrame, threshold: float = 0.5) -> dict[str, dict[str, float]]:
    """
    Computes pairwise correlations between numeric columns, only reporting
    pairs whose absolute correlation exceeds the threshold (weak correlations
    are noise, not insight).
    """
    numeric_df = df.select_dtypes(include="number")
    if numeric_df.shape[1] < 2:
        return {}

    corr_matrix = numeric_df.corr(numeric_only=True)
    result: dict[str, dict[str, float]] = {}

    for col_a in corr_matrix.columns:
        for col_b in corr_matrix.columns:
            if col_a >= col_b:  # Skip self-correlation and duplicate pairs (A-B vs B-A)
                continue
            corr_value = corr_matrix.loc[col_a, col_b]
            if pd.notna(corr_value) and abs(corr_value) >= threshold:
                result.setdefault(col_a, {})[col_b] = round(float(corr_value), 3)

    return result


def _detect_trends(df: pd.DataFrame) -> dict[str, str]:
    """
    Detects a simple overall trend direction (increasing/decreasing/stable)
    for numeric columns, based on comparing the first and second half of
    the data in row order.
    """
    trends: dict[str, str] = {}
    for column in df.select_dtypes(include="number").columns:
        series = df[column].dropna()
        if len(series) < 4:
            continue

        midpoint = len(series) // 2
        first_half_mean = series.iloc[:midpoint].mean()
        second_half_mean = series.iloc[midpoint:].mean()

        if first_half_mean == 0:
            continue

        percent_change = (second_half_mean - first_half_mean) / abs(first_half_mean) * 100

        if percent_change > 5:
            trends[column] = "increasing"
        elif percent_change < -5:
            trends[column] = "decreasing"
        else:
            trends[column] = "stable"

    return trends


def _generate_insights(
    numeric_summary: dict[str, dict[str, float]],
    correlations: dict[str, dict[str, float]],
    trends: dict[str, str],
    row_count: int,
) -> list[str]:
    """
    Converts computed statistics into plain-English insight statements,
    ready to display directly to the user.
    """
    insights: list[str] = [f"This dataset contains {row_count} rows."]

    for column, stats in numeric_summary.items():
        insights.append(
            f"'{column}' ranges from {stats['min']:.2f} to {stats['max']:.2f}, "
            f"averaging {stats['mean']:.2f}."
        )

    for column, trend in trends.items():
        if trend != "stable":
            insights.append(f"'{column}' shows a {trend} trend across the dataset.")

    for col_a, related in correlations.items():
        for col_b, corr_value in related.items():
            direction = "positive" if corr_value > 0 else "negative"
            insights.append(
                f"'{col_a}' and '{col_b}' have a strong {direction} correlation ({corr_value})."
            )

    return insights


def analyze_dataset(df: pd.DataFrame) -> AnalysisResult:
    """
    Runs the full analysis pipeline on a DataFrame and returns a structured
    result containing summaries, correlations, trends, and plain-English
    insight statements.

    Args:
        df: The (ideally already-cleaned) DataFrame to analyze.

    Returns:
        An AnalysisResult with all computed statistics and insights.
    """
    numeric_summary = _compute_numeric_summary(df)
    categorical_summary = _compute_categorical_summary(df)
    correlations = _compute_correlations(df)
    trends = _detect_trends(df)
    insights = _generate_insights(numeric_summary, correlations, trends, row_count=len(df))

    logger.info(
        f"Analysis complete: {len(numeric_summary)} numeric columns, "
        f"{len(correlations)} correlated pairs, {len(trends)} trends detected."
    )

    return AnalysisResult(
        numeric_summary=numeric_summary,
        categorical_summary=categorical_summary,
        correlations=correlations,
        trends=trends,
        insights=insights,
    )