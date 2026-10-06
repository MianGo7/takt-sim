"""Statistics over replications: confidence intervals, tables, and the Welch analysis.

Turns the indicators of independent replications into means with confidence
intervals and supports the choice of the warm-up period. Implements FR11.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from takt.experiment import LineIndicators, MachineIndicators, ReplicationResult

CONFIDENCE_LEVEL = 0.95


@dataclass(frozen=True)
class Estimate:
    """Mean of independent replications with its confidence interval.

    Attributes:
        mean: Sample mean.
        half_width: Half width of the t-based confidence interval, NaN for a
            single replication.
        n: Number of replications that entered the mean.
    """

    mean: float
    half_width: float
    n: int

    @property
    def lower(self) -> float:
        """Lower end of the confidence interval."""
        return self.mean - self.half_width

    @property
    def upper(self) -> float:
        """Upper end of the confidence interval."""
        return self.mean + self.half_width


def estimate(values: Sequence[float], level: float = CONFIDENCE_LEVEL) -> Estimate:
    """Return the mean and the t-based confidence interval of independent values.

    A replication without a value, such as the quality of a run that produced
    no part, is left out of the mean and of `n`. The t distribution is used
    because the number of replications is small and the variance is estimated
    from them. Implements FR11.
    """
    finite = np.array([v for v in values if math.isfinite(v)], dtype=float)
    if finite.size == 0:
        return Estimate(math.nan, math.nan, 0)
    mean = float(finite.mean())
    if finite.size < 2:
        return Estimate(mean, math.nan, int(finite.size))
    standard_error = float(finite.std(ddof=1)) / math.sqrt(finite.size)
    half_width = float(stats.t.ppf((1 + level) / 2, finite.size - 1)) * standard_error
    return Estimate(mean, half_width, int(finite.size))


def _machine_values(machines: Sequence[MachineIndicators]) -> dict[str, float]:
    values: dict[str, float] = {}
    for machine in machines:
        for field in (
            "availability",
            "repairs",
            "share_processing",
            "share_starved",
            "share_blocked",
            "share_awaiting_repair",
            "share_under_repair",
        ):
            values[f"{field}_{machine.name}"] = float(getattr(machine, field))
    values["availability_mean"] = _average([m.availability for m in machines])
    values["repairs_mean"] = _average([float(m.repairs) for m in machines])
    return values


def _average(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def flatten(indicators: LineIndicators) -> dict[str, float]:
    """Return every indicator of a replication under its name."""
    return {
        "parts_produced": float(indicators.parts_produced),
        "throughput_per_h": indicators.throughput_per_h,
        "mean_lead_time_h": indicators.mean_lead_time_h,
        "mean_wip_parts": indicators.mean_wip_parts,
        "parts_scrapped": float(indicators.parts_scrapped),
        "mean_quality": indicators.mean_quality,
        **_machine_values(indicators.machines),
    }


def replication_table(results: Sequence[ReplicationResult]) -> pd.DataFrame:
    """One row per replication with a column per indicator."""
    rows = [
        {
            "scenario": r.scenario,
            "replication": r.replication,
            "seed": r.seed,
            **flatten(r.indicators),
        }
        for r in results
    ]
    return pd.DataFrame(rows)


def summary_table(results: Sequence[ReplicationResult]) -> pd.DataFrame:
    """One row per scenario and indicator with the mean and its confidence interval."""
    table = replication_table(results)
    indicator_columns = [c for c in table.columns if c not in ("scenario", "replication", "seed")]
    rows = []
    for scenario, group in table.groupby("scenario", sort=False):
        for column in indicator_columns:
            e = estimate(group[column].tolist())
            rows.append(
                {
                    "scenario": scenario,
                    "indicator": column,
                    "mean": e.mean,
                    "half_width": e.half_width,
                    "lower": e.lower,
                    "upper": e.upper,
                    "n": e.n,
                    "confidence_level": CONFIDENCE_LEVEL,
                }
            )
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class WelchResult:
    """Outcome of the Welch analysis of the initial transient.

    Attributes:
        averaged: The mean of the series over the replications.
        smoothed: The moving average of the averaged series.
        plateau_mean: Mean of the second half of the smoothed series.
    """

    averaged: tuple[float, ...]
    smoothed: tuple[float, ...]
    plateau_mean: float


def moving_average(series: Sequence[float], window: int) -> list[float]:
    """Centred moving average of Welch, with a shrinking window at the start.

    The value at position i, counted from zero, averages the positions from
    i - window to i + window, and the first positions use the symmetric
    window that fits. The last `window` positions are dropped, because their
    window is incomplete.
    """
    n = len(series)
    smoothed = []
    for i in range(n - window):
        half = min(i, window)
        smoothed.append(math.fsum(series[i - half : i + half + 1]) / (2 * half + 1))
    return smoothed


def welch(series_per_replication: Sequence[Sequence[float]], window: int) -> WelchResult:
    """Apply the procedure of Welch to the series of independent replications.

    The series are averaged over the replications and smoothed with a moving
    average, so that the curve can be inspected and recorded.
    """
    averaged = np.mean(np.array(series_per_replication, dtype=float), axis=0).tolist()
    smoothed = moving_average(averaged, window)
    return WelchResult(tuple(averaged), tuple(smoothed), _average(smoothed[len(smoothed) // 2 :]))


def mser_truncation(series: Sequence[float], max_fraction: float = 0.5) -> int:
    """Return the truncation point that minimises the marginal standard error.

    For every candidate d the statistic is the sum of the squared deviations
    of the remaining observations from their mean, divided by the square of
    their number (White, 1997). The rule needs no tolerance, so the choice
    follows from the data and can be repeated (ADR-0011). Candidates are
    limited to the first `max_fraction` of the series.
    """
    n = len(series)
    best_d, best_value = 0, math.inf
    for d in range(int(n * max_fraction) + 1):
        rest = series[d:]
        mean = _average(rest)
        value = math.fsum((y - mean) ** 2 for y in rest) / len(rest) ** 2
        if value < best_value:
            best_d, best_value = d, value
    return best_d
