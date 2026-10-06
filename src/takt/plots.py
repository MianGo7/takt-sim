"""Figures of the results: black on white, with 95 percent confidence intervals.

The only module that imports Matplotlib. Every function takes the summary
table of an experiment, as produced by `analysis.summary_table`, and writes
one figure as PDF and as PNG at 300 dots per inch. Implements FR13.
"""

from collections.abc import Sequence
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

# A file backend, so that the figures are written without a display. Chosen
# before the first figure is created.
matplotlib.use("Agg")

DOTS_PER_INCH = 300
MARKERS = ("o", "s", "^", "D", "v")
LINE_STYLES = ("-", "--", "-.", ":", (0, (5, 1)))

# Percent for the availability, as in the reference case, and the plain value
# for everything else.
LABELS = {
    "parts_produced": ("Parts produced per run", "parts", 1.0),
    "mean_lead_time_h": ("Mean lead time", "hours", 1.0),
    "mean_wip_parts": ("Mean work in progress", "parts", 1.0),
    "availability_mean": ("Mean machine availability", "percent", 100.0),
    "repairs_mean": ("Repairs per machine", "repairs", 1.0),
    "mean_quality": ("Mean product quality", "index from 0 to 1", 1.0),
    "parts_scrapped": ("Parts scrapped per run", "parts", 1.0),
}


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
            "font.size": 9,
            "axes.edgecolor": "black",
            "axes.labelcolor": "black",
            "xtick.color": "black",
            "ytick.color": "black",
            "text.color": "black",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def save_figure(figure: Figure, base: Path) -> list[Path]:
    """Write the figure as `<base>.pdf` and `<base>.png` and close it."""
    base.parent.mkdir(parents=True, exist_ok=True)
    paths = [base.with_suffix(".pdf"), base.with_suffix(".png")]
    for path in paths:
        figure.savefig(path, dpi=DOTS_PER_INCH, bbox_inches="tight")
    plt.close(figure)
    return paths


def _axis_label(indicator: str) -> str:
    title, unit, _ = LABELS[indicator]
    return f"{title} ({unit})"


def _points(
    summary: pd.DataFrame, indicator: str, x_column: str
) -> tuple[list[float], list[float], list[float]]:
    rows = summary[summary["indicator"] == indicator].sort_values(x_column)
    factor = LABELS[indicator][2]
    return (
        rows[x_column].tolist(),
        (rows["mean"] * factor).tolist(),
        (rows["half_width"] * factor).tolist(),
    )


def _draw_series(
    ax: Axes,
    summary: pd.DataFrame,
    indicator: str,
    x_column: str,
    index: int,
    label: str | None,
) -> None:
    x, mean, half_width = _points(summary, indicator, x_column)
    ax.errorbar(
        x,
        mean,
        yerr=half_width,
        color="black",
        marker=MARKERS[index % len(MARKERS)],
        markerfacecolor="white" if index % 2 else "black",
        linestyle=LINE_STYLES[index % len(LINE_STYLES)],
        linewidth=1.0,
        markersize=4,
        capsize=2,
        label=label,
    )


def _panels(indicators: Sequence[str], columns: int) -> tuple[Figure, list[Axes]]:
    _style()
    rows = -(-len(indicators) // columns)
    figure, axes = plt.subplots(rows, columns, figsize=(3.1 * columns, 2.6 * rows))
    flat = list(axes.ravel()) if hasattr(axes, "ravel") else [axes]
    for unused in flat[len(indicators) :]:
        unused.set_visible(False)
    return figure, flat


def threshold_figure(summary: pd.DataFrame, reference: pd.DataFrame, base: Path) -> list[Path]:
    """Indicators of S2 against the alarm threshold, with S1 as a dashed line.

    The reference is the summary of S1. Its mean is a horizontal dashed line
    and its confidence interval a grey band.
    """
    indicators = (
        "parts_produced",
        "mean_lead_time_h",
        "mean_wip_parts",
        "availability_mean",
        "repairs_mean",
        "mean_quality",
    )
    figure, axes = _panels(indicators, 3)
    for ax, indicator in zip(axes, indicators, strict=False):
        _draw_series(ax, summary, indicator, "setting_alarm_threshold", 0, "S2, ideal signal")
        row = reference[reference["indicator"] == indicator].iloc[0]
        factor = LABELS[indicator][2]
        ax.axhline(row["mean"] * factor, color="black", linestyle="--", linewidth=0.8, label="S1")
        ax.axhspan(row["lower"] * factor, row["upper"] * factor, color="0.85", linewidth=0)
        ax.set_xlabel("Alarm threshold (health)")
        ax.set_ylabel(_axis_label(indicator))
    axes[0].legend(frameon=False, loc="best")
    figure.tight_layout()
    return save_figure(figure, base)


def signal_figure(summary: pd.DataFrame, base: Path) -> list[Path]:
    """Indicators of S3 against the false alarm probability, one line per detection probability."""
    indicators = ("parts_produced", "mean_quality", "repairs_mean")
    figure, axes = _panels(indicators, 3)
    detections = sorted(summary["setting_detection_probability"].unique(), reverse=True)
    false_alarms = sorted(summary["setting_false_alarm_probability"].unique())
    # Equal spacing, because the probabilities are not equally spaced.
    position = {value: index for index, value in enumerate(false_alarms)}
    for ax, indicator in zip(axes, indicators, strict=False):
        for index, detection in enumerate(detections):
            subset = summary[summary["setting_detection_probability"] == detection].copy()
            subset["position"] = subset["setting_false_alarm_probability"].map(position)
            _draw_series(ax, subset, indicator, "position", index, f"detection {detection:g}")
        ax.set_xticks(list(position.values()), [f"{v:g}" for v in false_alarms])
        ax.set_xlabel("False alarm probability per reading (probability)")
        ax.set_ylabel(_axis_label(indicator))
    axes[0].legend(frameon=False, loc="best", title="Detection probability")
    figure.tight_layout()
    return save_figure(figure, base)


def buffer_figure(summary: pd.DataFrame, base: Path) -> list[Path]:
    """Indicators of S4 against the buffer capacity for both policies."""
    indicators = ("parts_produced", "mean_wip_parts", "mean_lead_time_h")
    figure, axes = _panels(indicators, 3)
    names = {0.0: "S1, run-to-failure", 1.0: "Condition-based"}
    for ax, indicator in zip(axes, indicators, strict=False):
        for index, (flag, name) in enumerate(names.items()):
            subset = summary[summary["setting_condition_based"] == flag]
            _draw_series(ax, subset, indicator, "setting_buffer_capacity", index, name)
        ax.set_xlabel("Buffer capacity (parts)")
        ax.set_ylabel(_axis_label(indicator))
    axes[0].legend(frameon=False, loc="best")
    figure.tight_layout()
    return save_figure(figure, base)
