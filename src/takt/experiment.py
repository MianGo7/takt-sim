"""Experiments: scenarios run in replications and reduced to indicators.

An experiment is defined completely by an `ExperimentConfig`, so that it can
be repeated from its definition alone. The replications of all scenarios use
the same seeds, which gives common random numbers (ADR-0011). The warm-up
period is cut off here, and the model knows nothing about it. Implements
FR10 to FR12.
"""

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import numpy as np

from takt.config import LineConfig, RunConfig, reference_line_with_degradation
from takt.model import LineResult, MachineState, RepairKind, run_line

type Trace[T] = Sequence[tuple[float, T]]

# ADR-0011: the warm-up period is the larger of the two truncation points that
# the marginal standard error rule finds for the output and the work in
# progress of S1 (252 hours and 132 hours).
WARMUP_H = 252.0
REPLICATIONS = 50  # p. 420
RUN_LENGTH_H = 10_080.0  # p. 420, the observed period after the warm-up
DEFAULT_SEED = 2026


@dataclass(frozen=True)
class Scenario:
    """A named configuration of the line.

    Attributes:
        name: Short identifier such as S1.
        line: The line with its degradation and repair settings.
    """

    name: str
    line: LineConfig


@dataclass(frozen=True)
class ExperimentConfig:
    """Everything that is needed to repeat an experiment.

    Attributes:
        name: Identifier of the experiment, used for the output folder.
        scenarios: The scenarios that are compared.
        seed: Root seed from which the replication seeds are derived.
        replications: Number of independent replications per scenario.
        warmup_h: Simulated hours before the observation starts.
        run_length_h: Observed hours after the warm-up period.
    """

    name: str
    scenarios: tuple[Scenario, ...]
    seed: int = DEFAULT_SEED
    replications: int = REPLICATIONS
    warmup_h: float = WARMUP_H
    run_length_h: float = RUN_LENGTH_H

    def __post_init__(self) -> None:
        """Validate the number of replications, the warm-up, and the run length."""
        if self.replications < 1:
            raise ValueError(f"replications must be at least 1, got {self.replications}")
        if self.warmup_h < 0 or not math.isfinite(self.warmup_h):
            raise ValueError(f"warmup_h must not be negative, got {self.warmup_h}")
        if self.run_length_h <= 0 or not math.isfinite(self.run_length_h):
            raise ValueError(f"run_length_h must be positive, got {self.run_length_h}")
        if not self.scenarios:
            raise ValueError("an experiment needs at least one scenario")


@dataclass(frozen=True)
class MachineIndicators:
    """Indicators of one machine over the observed period.

    Attributes:
        name: Name of the machine.
        availability: Share of the time in which the machine was neither
            awaiting nor under repair (p. 419).
        repairs: Repairs completed in the period, corrective and preventive.
        repairs_preventive: Preventive repairs among them, which include the
            repairs that a false alarm causes.
        share_processing: Share of the time spent processing.
        share_starved: Share of the time spent waiting for a part.
        share_blocked: Share of the time spent waiting for buffer space.
        share_awaiting_repair: Share of the time spent waiting for a maintainer.
        share_under_repair: Share of the time under repair.
    """

    name: str
    availability: float
    repairs: int
    repairs_preventive: int
    share_processing: float
    share_starved: float
    share_blocked: float
    share_awaiting_repair: float
    share_under_repair: float


@dataclass(frozen=True)
class LineIndicators:
    """Indicators of the line over the observed period.

    Attributes:
        parts_produced: Parts that reached the sink in the period.
        throughput_per_h: Parts produced per hour.
        mean_lead_time_h: Mean lead time of the produced parts in hours, or
            NaN if none was produced.
        mean_wip_parts: Time average of the parts waiting in all buffers
            (p. 419).
        parts_scrapped: Parts scrapped by failures in the period.
        mean_quality: Mean quality of the produced parts, or NaN if none was
            produced.
        std_quality: Sample standard deviation of the quality of the produced
            parts, or NaN with fewer than two parts.
        failures_while_processing: Failures of machines that were processing a
            part, which scraps it.
        failures_while_starved: Failures of machines that were waiting for a
            part.
        failures_while_blocked: Failures of machines that held a finished part,
            which is not scrapped (A9).
        alarms_true: Alarms in the period that created a work order and were
            read at or below the alarm threshold.
        alarms_false: Alarms in the period that created a work order and were
            read above the alarm threshold.
        machines: The indicators of every machine.
    """

    parts_produced: int
    throughput_per_h: float
    mean_lead_time_h: float
    mean_wip_parts: float
    parts_scrapped: int
    mean_quality: float
    std_quality: float
    failures_while_processing: int
    failures_while_starved: int
    failures_while_blocked: int
    alarms_true: int
    alarms_false: int
    machines: tuple[MachineIndicators, ...]


@dataclass(frozen=True)
class ReplicationResult:
    """The indicators of one replication of one scenario.

    Attributes:
        scenario: Name of the scenario.
        replication: Index of the replication, starting at zero.
        seed: Seed of the replication, equal across scenarios.
        indicators: The indicators over the observed period.
    """

    scenario: str
    replication: int
    seed: int
    indicators: LineIndicators


def replication_seeds(root_seed: int, count: int) -> list[int]:
    """Derive one seed per replication from the root seed.

    The seeds do not depend on the scenario, so that every scenario sees the
    same degradation events in the same replication (ADR-0011). Implements
    FR12.
    """
    children = np.random.SeedSequence(root_seed).spawn(count)
    return [int(child.generate_state(1, dtype=np.uint64)[0]) for child in children]


def _segments[T](trace: Trace[T], start_h: float, end_h: float) -> Iterator[tuple[T, float]]:
    """Yield each value of a step trace with its duration inside the window."""
    ends = [time_h for time_h, _ in trace[1:]] + [end_h]
    for (begin_h, value), finish_h in zip(trace, ends, strict=True):
        duration_h = min(finish_h, end_h) - max(begin_h, start_h)
        if duration_h > 0:
            yield value, duration_h


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values) if values else math.nan


def _std(values: Sequence[float]) -> float:
    if len(values) < 2:
        return math.nan
    mean = _mean(values)
    return math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (len(values) - 1))


def _failures_by_state(result: LineResult, start_h: float, end_h: float) -> dict[MachineState, int]:
    """Count the failures in the window by the state the machine was in before."""
    counts = dict.fromkeys(MachineState, 0)
    for failures in result.failures:
        for time_h, before in failures:
            if start_h <= time_h < end_h:
                counts[before] += 1
    return counts


def line_indicators(result: LineResult, start_h: float, end_h: float) -> LineIndicators:
    """Reduce the raw output of a run to the indicators of the window.

    Parts, scrapped parts, and repairs count by the time at which they
    happen, and the half-open window follows ADR-0008. Implements FR10.
    """
    window_h = end_h - start_h
    parts = [p for p in result.parts if start_h <= p.completed_at_h < end_h]
    wip_part_h = math.fsum(
        level * duration_h
        for trace in result.buffer_level_traces
        for level, duration_h in _segments(trace, start_h, end_h)
    )
    machines = tuple(
        _machine_indicators(index, result, start_h, end_h)
        for index in range(len(result.machine_state_traces))
    )
    scrapped = sum(1 for times in result.scrap_times_h for t in times if start_h <= t < end_h)
    failures = _failures_by_state(result, start_h, end_h)
    return LineIndicators(
        parts_produced=len(parts),
        throughput_per_h=len(parts) / window_h,
        mean_lead_time_h=_mean([p.lead_time_h for p in parts]),
        mean_wip_parts=wip_part_h / window_h,
        parts_scrapped=scrapped,
        mean_quality=_mean([p.quality for p in parts]),
        std_quality=_std([p.quality for p in parts]),
        failures_while_processing=failures[MachineState.PROCESSING],
        failures_while_starved=failures[MachineState.STARVED],
        failures_while_blocked=failures[MachineState.BLOCKED],
        alarms_true=sum(1 for a in result.alarms if a.true_alarm and start_h <= a.time_h < end_h),
        alarms_false=sum(
            1 for a in result.alarms if not a.true_alarm and start_h <= a.time_h < end_h
        ),
        machines=machines,
    )


def _machine_indicators(
    index: int, result: LineResult, start_h: float, end_h: float
) -> MachineIndicators:
    name = f"M{index + 1}"
    window_h = end_h - start_h
    time_in = dict.fromkeys(MachineState, 0.0)
    for state, duration_h in _segments(result.machine_state_traces[index], start_h, end_h):
        time_in[state] += duration_h
    down_h = time_in[MachineState.AWAITING_REPAIR] + time_in[MachineState.UNDER_REPAIR]
    done = [r for r in result.repairs if r.machine == name and start_h <= r.finished_at_h < end_h]
    return MachineIndicators(
        name=name,
        availability=(window_h - down_h) / window_h,
        repairs=len(done),
        repairs_preventive=sum(1 for r in done if r.kind is RepairKind.PREVENTIVE),
        share_processing=time_in[MachineState.PROCESSING] / window_h,
        share_starved=time_in[MachineState.STARVED] / window_h,
        share_blocked=time_in[MachineState.BLOCKED] / window_h,
        share_awaiting_repair=time_in[MachineState.AWAITING_REPAIR] / window_h,
        share_under_repair=time_in[MachineState.UNDER_REPAIR] / window_h,
    )


def binned_series(result: LineResult, bin_h: float) -> tuple[list[float], list[float]]:
    """Return the parts produced and the mean work in progress per bin.

    The two series are the input of the analysis of the initial transient
    (ADR-0011). Only complete bins are returned.
    """
    bins = int(result.run_length_h // bin_h)
    output = [0.0] * bins
    for part in result.parts:
        index = int(part.completed_at_h // bin_h)
        if index < bins:
            output[index] += 1.0
    wip = [
        math.fsum(
            level * duration_h
            for trace in result.buffer_level_traces
            for level, duration_h in _segments(trace, i * bin_h, (i + 1) * bin_h)
        )
        / bin_h
        for i in range(bins)
    ]
    return output, wip


def run_experiment(config: ExperimentConfig) -> list[ReplicationResult]:
    """Run every scenario in every replication and return the indicators.

    The seeds are shared by the scenarios, and the warm-up period is simulated
    and then excluded from the indicators (ADR-0011). Implements FR11 and
    FR12.
    """
    seeds = replication_seeds(config.seed, config.replications)
    end_h = config.warmup_h + config.run_length_h
    results: list[ReplicationResult] = []
    for scenario in config.scenarios:
        for replication, seed in enumerate(seeds):
            raw = run_line(scenario.line, RunConfig(run_length_h=end_h, seed=seed))
            indicators = line_indicators(raw, config.warmup_h, end_h)
            results.append(ReplicationResult(scenario.name, replication, seed, indicators))
    return results


def s0_experiment() -> ExperimentConfig:
    """Scenario S0, the deterministic line without degradation, for verification."""
    # The line is deterministic and has no random initial transient, so the
    # indicators are taken from time zero and compare with exact values.
    return ExperimentConfig(
        name="s0", scenarios=(Scenario("S0", LineConfig()),), replications=1, warmup_h=0.0
    )


def s1_experiment() -> ExperimentConfig:
    """Scenario S1, run-to-failure, with the settings of the reference case."""
    scenario = Scenario("S1", reference_line_with_degradation())
    return ExperimentConfig(name="s1", scenarios=(scenario,))


def s1_from_start_experiment() -> ExperimentConfig:
    """Scenario S1 observed from time zero, the setting of the reference case.

    The paper reports the indicators of the whole run of 10,080 hours without
    a warm-up period (p. 420), so this variant is the like for like
    comparison with it (ADR-0011).
    """
    scenario = Scenario("S1", reference_line_with_degradation())
    return ExperimentConfig(name="s1-from-start", scenarios=(scenario,), warmup_h=0.0)


EXPERIMENTS = {
    "s0": s0_experiment,
    "s1": s1_experiment,
    "s1-from-start": s1_from_start_experiment,
}
