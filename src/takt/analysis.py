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
            "repairs_preventive",
            "share_processing",
            "share_starved",
            "share_blocked",
            "share_awaiting_repair",
            "share_under_repair",
        ):
            values[f"{field}_{machine.name}"] = float(getattr(machine, field))
    values["availability_mean"] = _average([m.availability for m in machines])
    values["repairs_mean"] = _average([float(m.repairs) for m in machines])
    values["repairs_preventive_mean"] = _average([float(m.repairs_preventive) for m in machines])
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
        "std_quality": indicators.std_quality,
        "failures_while_processing": float(indicators.failures_while_processing),
        "failures_while_starved": float(indicators.failures_while_starved),
        "failures_while_blocked": float(indicators.failures_while_blocked),
        "alarms_true": float(indicators.alarms_true),
        "alarms_false": float(indicators.alarms_false),
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


@dataclass(frozen=True)
class PublishedValue:
    """A published mean of the reference case with its spread.

    Attributes:
        indicator: Name of the indicator in `flatten`.
        mean: Published mean.
        spread: Published value after the plus-minus sign.
        spread_over: What the spread is taken over: "replications" when it is
            the standard deviation of the replications, "machines" for the
            availability and the repair count, whose published spread equals
            the spread across the six machines (concept.md), and "unspecified"
            when the paper does not say.
        resolution: Half of the last printed digit, the rounding of the paper.
    """

    indicator: str
    mean: float
    spread: float
    spread_over: str
    resolution: float


PUBLISHED_REPLICATIONS = 50  # p. 420

# Dadfarnia et al. (2023), Table I on p. 421, test scenario {C1, Pi1}. The
# availability is stored as a fraction, the paper prints it in percent.
PUBLISHED_C1_RUN_TO_FAILURE = (
    PublishedValue("availability_mean", 0.7670, 0.09484, "machines", 0.00005),
    PublishedValue("repairs_mean", 115.12, 47.427, "machines", 0.005),
    PublishedValue("parts_produced", 4730.16, 53.638, "replications", 0.005),
    PublishedValue("mean_quality", 0.60, 0.123, "unspecified", 0.005),
)


def _spread_of_ours(table: pd.DataFrame, indicator: str, spread_over: str) -> float:
    """Return the spread of our model in the sense in which the paper gives it."""
    if spread_over == "replications":
        return float(table[indicator].std(ddof=1))
    if spread_over == "machines":
        name = indicator.removesuffix("_mean")
        columns = [c for c in table.columns if c.startswith(f"{name}_M")]
        return float(np.std(table[columns].to_numpy().ravel(), ddof=1))
    return float(table["std_quality"].mean())


def compare_with_published(
    results: Sequence[ReplicationResult],
    published: Sequence[PublishedValue] = PUBLISHED_C1_RUN_TO_FAILURE,
    published_replications: int = PUBLISHED_REPLICATIONS,
) -> pd.DataFrame:
    """Compare the means of one scenario with the published means.

    A mean agrees when its difference from the published mean is no larger
    than the half width of the confidence interval plus the rounding of the
    paper. The difference is also expressed as a z value over the standard
    errors of both means. Where the published spread is the standard deviation
    of the replications, the standard error of the published mean follows from
    it. For the other spreads it cannot be derived, and the standard deviation
    of the replications of this model stands in for it, which assumes that the
    published model varies as much as this one. The column
    `published_se_known` tells the two cases apart. The spread of the model
    is computed in the same sense as the published one, as far as the paper
    states it.
    """
    table = replication_table(results)
    rows = []
    for item in published:
        values = table[item.indicator].tolist()
        e = estimate(values)
        difference = e.mean - item.mean
        replication_sd = float(np.std(values, ddof=1))
        own_se = replication_sd / math.sqrt(len(values))
        known = item.spread_over == "replications"
        published_sd = item.spread if known else replication_sd
        published_se = published_sd / math.sqrt(published_replications)
        z = difference / math.hypot(own_se, published_se)
        rows.append(
            {
                "indicator": item.indicator,
                "published_mean": item.mean,
                "published_spread": item.spread,
                "spread_over": item.spread_over,
                "mean": e.mean,
                "half_width": e.half_width,
                "difference": difference,
                "agrees_within_ci_and_rounding": abs(difference) <= e.half_width + item.resolution,
                "z_over_both_standard_errors": z,
                "published_se_known": known,
                "spread": _spread_of_ours(table, item.indicator, item.spread_over),
                "replications": e.n,
            }
        )
    return pd.DataFrame(rows)
