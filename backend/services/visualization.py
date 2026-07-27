"""
backend/services/visualization.py

Chart generation utilities for InsightAI.

Responsibilities:
- Generate matplotlib chart images (PNG) saved to disk, for embedding in reports
- Generate chart-ready JSON data structures for frontend rendering (Chart.js/Plotly)
- Automatically select sensible chart types based on column data types
"""

import uuid
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Non-interactive backend — required for server-side rendering (no display).

import matplotlib.pyplot as plt
import pandas as pd
from loguru import logger


def _save_figure(fig: plt.Figure, charts_dir: str, chart_name: str) -> str:
    """Saves a matplotlib figure to disk as a PNG and returns the file path."""
    charts_path = Path(charts_dir)
    charts_path.mkdir(parents=True, exist_ok=True)

    filename = f"{chart_name}_{uuid.uuid4().hex[:8]}.png"
    file_path = charts_path / filename

    fig.savefig(file_path, bbox_inches="tight", dpi=100)
    plt.close(fig)

    return str(file_path)


def generate_histogram(df: pd.DataFrame, column: str, charts_dir: str) -> str:
    """Generates and saves a histogram for a numeric column. Returns the file path."""
    fig, ax = plt.subplots(figsize=(8, 5))
    df[column].dropna().hist(ax=ax, bins=20, color="#4C72B0", edgecolor="white")
    ax.set_title(f"Distribution of {column}")
    ax.set_xlabel(column)
    ax.set_ylabel("Frequency")
    return _save_figure(fig, charts_dir, f"histogram_{column}")


def generate_bar_chart(df: pd.DataFrame, column: str, charts_dir: str, top_n: int = 10) -> str:
    """Generates and saves a bar chart of the top N most frequent values in a categorical column."""
    value_counts = df[column].value_counts().head(top_n)

    fig, ax = plt.subplots(figsize=(8, 5))
    value_counts.plot(kind="bar", ax=ax, color="#55A868", edgecolor="white")
    ax.set_title(f"Top {top_n} values in {column}")
    ax.set_xlabel(column)
    ax.set_ylabel("Count")
    plt.xticks(rotation=45, ha="right")
    return _save_figure(fig, charts_dir, f"barchart_{column}")


def generate_correlation_heatmap(df: pd.DataFrame, charts_dir: str) -> str | None:
    """
    Generates and saves a correlation heatmap for all numeric columns.
    Returns None if there are fewer than 2 numeric columns (no correlation possible).
    """
    numeric_df = df.select_dtypes(include="number")
    if numeric_df.shape[1] < 2:
        return None

    corr_matrix = numeric_df.corr(numeric_only=True)

    fig, ax = plt.subplots(figsize=(8, 6))
    cax = ax.matshow(corr_matrix, cmap="coolwarm", vmin=-1, vmax=1)
    fig.colorbar(cax)

    ax.set_xticks(range(len(corr_matrix.columns)))
    ax.set_yticks(range(len(corr_matrix.columns)))
    ax.set_xticklabels(corr_matrix.columns, rotation=45, ha="left")
    ax.set_yticklabels(corr_matrix.columns)
    ax.set_title("Correlation Heatmap", pad=20)

    return _save_figure(fig, charts_dir, "correlation_heatmap")


def generate_all_charts(df: pd.DataFrame, charts_dir: str, max_charts_per_type: int = 3) -> list[str]:
    """
    Automatically generates a sensible set of charts for a dataset:
    - Histograms for up to `max_charts_per_type` numeric columns
    - Bar charts for up to `max_charts_per_type` categorical columns
    - One correlation heatmap (if enough numeric columns exist)

    Returns a list of file paths to the generated chart images.
    """
    chart_paths: list[str] = []

    numeric_columns = df.select_dtypes(include="number").columns[:max_charts_per_type]
    for column in numeric_columns:
        try:
            chart_paths.append(generate_histogram(df, column, charts_dir))
        except Exception as exc:
            logger.warning(f"Failed to generate histogram for '{column}': {exc}")

    categorical_columns = df.select_dtypes(include="object").columns[:max_charts_per_type]
    for column in categorical_columns:
        try:
            chart_paths.append(generate_bar_chart(df, column, charts_dir))
        except Exception as exc:
            logger.warning(f"Failed to generate bar chart for '{column}': {exc}")

    heatmap_path = generate_correlation_heatmap(df, charts_dir)
    if heatmap_path:
        chart_paths.append(heatmap_path)

    logger.info(f"Generated {len(chart_paths)} chart images.")
    return chart_paths


def build_chart_json(df: pd.DataFrame, max_columns: int = 5) -> dict:
    """
    Builds a JSON-serializable dict of chart data for frontend rendering
    with Chart.js or Plotly — no image files, just structured data points.

    Returns a dict with:
        - "numeric": {column: {"labels": [...], "values": [...]}} for histograms
        - "categorical": {column: {"labels": [...], "values": [...]}} for bar charts
    """
    result: dict = {"numeric": {}, "categorical": {}}

    numeric_columns = df.select_dtypes(include="number").columns[:max_columns]
    for column in numeric_columns:
        series = df[column].dropna()
        if series.empty:
            continue
        # Bin into 10 buckets for a lightweight histogram-style dataset.
        counts, bin_edges = pd.cut(series, bins=10, retbins=True)
        value_counts = counts.value_counts(sort=False)
        result["numeric"][column] = {
            "labels": [f"{bin_edges[i]:.1f}-{bin_edges[i+1]:.1f}" for i in range(len(bin_edges) - 1)],
            "values": value_counts.tolist(),
        }

    categorical_columns = df.select_dtypes(include="object").columns[:max_columns]
    for column in categorical_columns:
        value_counts = df[column].value_counts().head(10)
        result["categorical"][column] = {
            "labels": value_counts.index.astype(str).tolist(),
            "values": value_counts.tolist(),
        }

    return result