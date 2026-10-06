"""Parameters of the line and of a run as immutable data.

The defaults are the serial configuration of the reference case (Dadfarnia et
al., 2023, p. 420). Every field carries its unit in its name, and the values
are validated on construction. Implements NFR4.
"""

import dataclasses
import math
from dataclasses import dataclass, field

MACHINES_IN_SERIES = 6  # p. 420
BUFFER_CAPACITY_PARTS = 10  # p. 420
CYCLE_TIME_H = 1.0  # p. 420, derived from a path of 6 hours over 6 machines
ARRIVAL_INTERVAL_H = 1.0  # p. 420, an arrival rate of one part per hour
RUN_LENGTH_H = 10_080.0  # p. 420
HEALTH_STEPS = 8  # p. 417, nine health values from 1 down to 0 in steps of 0.125
MAINTAINERS = 3  # p. 420
CORRECTIVE_REPAIR_TIME_H = 20.0  # pp. 418, 422
DETERIORATED_REPAIR_TIME_H = 5.0  # pp. 419, 422, health above 0 and below 0.5
MILD_REPAIR_TIME_H = 2.5  # pp. 419, 422, health of 0.5 or more (A6)
MILD_HEALTH_LIMIT = 0.5  # p. 419
SENSING_INTERVAL_H = 1.0  # pp. 418, 422
REGULAR_WEIBULL_SHAPE = 1.5  # pp. 417, 420, machines M1, M2, M4, M5, M6
REGULAR_WEIBULL_SCALE_H = 12.0  # pp. 417, 420, unit by A1
M3_WEIBULL_SHAPE = 0.9  # pp. 417, 420
M3_WEIBULL_SCALE_H = 3.0  # pp. 417, 420, unit by A1


def _require_positive_finite(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number, got {value}")


@dataclass(frozen=True)
class DegradationConfig:
    """Weibull distribution of the time between two degradation events.

    Implements FR3.

    Attributes:
        weibull_shape: Shape parameter of the distribution.
        weibull_scale_h: Scale parameter in hours (A1).
    """

    weibull_shape: float
    weibull_scale_h: float

    def __post_init__(self) -> None:
        """Validate both parameters."""
        _require_positive_finite("weibull_shape", self.weibull_shape)
        _require_positive_finite("weibull_scale_h", self.weibull_scale_h)


@dataclass(frozen=True)
class MachineConfig:
    """Parameters of one machine.

    Implements FR1 and FR3.

    Attributes:
        cycle_time_h: Constant processing time of one part in hours (A3).
        degradation: Degradation of the machine, or None for a machine that
            never degrades, which is the setting of scenario S0.
    """

    cycle_time_h: float = CYCLE_TIME_H
    degradation: DegradationConfig | None = None

    def __post_init__(self) -> None:
        """Validate the cycle time."""
        _require_positive_finite("cycle_time_h", self.cycle_time_h)


@dataclass(frozen=True)
class BufferConfig:
    """Parameters of one buffer.

    Implements FR2.

    Attributes:
        capacity_parts: Number of parts the buffer holds. A capacity of zero
            is a rendezvous between two machines (ADR-0012).
    """

    capacity_parts: int = BUFFER_CAPACITY_PARTS

    def __post_init__(self) -> None:
        """Validate the capacity."""
        if self.capacity_parts < 0:
            raise ValueError(f"capacity_parts must not be negative, got {self.capacity_parts}")


@dataclass(frozen=True)
class RepairConfig:
    """Maintainers and the duration of a repair by the health of the machine.

    Implements FR4 to FR6.

    Attributes:
        maintainers: Number of repairs that can run at the same time.
        corrective_repair_time_h: Constant duration in hours of the repair of
            a failed machine (A4).
        deteriorated_repair_time_h: Duration in hours of a repair at a health
            above 0 and below 0.5.
        mild_repair_time_h: Duration in hours of a repair at a health of 0.5
            or more, which includes 0.5 itself (A6).
    """

    maintainers: int = MAINTAINERS
    corrective_repair_time_h: float = CORRECTIVE_REPAIR_TIME_H
    deteriorated_repair_time_h: float = DETERIORATED_REPAIR_TIME_H
    mild_repair_time_h: float = MILD_REPAIR_TIME_H

    def __post_init__(self) -> None:
        """Validate the number of maintainers and the repair times."""
        if self.maintainers < 1:
            raise ValueError(f"maintainers must be at least 1, got {self.maintainers}")
        _require_positive_finite("corrective_repair_time_h", self.corrective_repair_time_h)
        _require_positive_finite("deteriorated_repair_time_h", self.deteriorated_repair_time_h)
        _require_positive_finite("mild_repair_time_h", self.mild_repair_time_h)

    def repair_time_h(self, health: float) -> float:
        """Return the duration of a repair that starts at the given health."""
        if health <= 0.0:
            return self.corrective_repair_time_h
        if health < MILD_HEALTH_LIMIT:
            return self.deteriorated_repair_time_h
        return self.mild_repair_time_h


@dataclass(frozen=True)
class RunToFailureConfig:
    """Maintenance policy without monitoring: a machine is repaired when it fails.

    Implements FR4. This is scenario S1.
    """


@dataclass(frozen=True)
class ConditionBasedConfig:
    """Maintenance policy with a monitoring system that reads the health.

    Implements FR7 and FR8. The defaults describe an ideal signal. The error
    rates are not taken from the reference case, they are the variables of
    scenario S3 (ADR-0006).

    Attributes:
        alarm_threshold: A reading at or below this health is an alarm. A value
            below the smallest health that is not zero never raises an alarm
            for a working machine.
        sensing_interval_h: Time in hours between two readings (pp. 418, 422).
        detection_probability: Probability that a reading at or below the
            threshold raises an alarm. One means no missed alarms.
        false_alarm_probability: Probability that a reading above the threshold
            raises an alarm. Zero means no false alarms.
    """

    alarm_threshold: float
    sensing_interval_h: float = SENSING_INTERVAL_H
    detection_probability: float = 1.0
    false_alarm_probability: float = 0.0

    def __post_init__(self) -> None:
        """Validate the threshold, the interval, and the probabilities."""
        if not 0.0 <= self.alarm_threshold <= 1.0:
            raise ValueError(f"alarm_threshold must lie in [0, 1], got {self.alarm_threshold}")
        _require_positive_finite("sensing_interval_h", self.sensing_interval_h)
        for name in ("detection_probability", "false_alarm_probability"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must lie in [0, 1], got {value}")


def _reference_machines() -> tuple[MachineConfig, ...]:
    return tuple(MachineConfig() for _ in range(MACHINES_IN_SERIES))


def _reference_buffers() -> tuple[BufferConfig, ...]:
    return tuple(BufferConfig() for _ in range(MACHINES_IN_SERIES - 1))


@dataclass(frozen=True)
class LineConfig:
    """Layout and parameters of a serial line, by default the reference case.

    Implements FR1 and FR2.

    Attributes:
        machines: The machines in the order of the flow.
        buffers: The buffers between neighbouring machines, one fewer than
            machines.
        arrival_interval_h: Time in hours between the offers of the source
            (A7).
        repair: The maintainers and the repair times.
        policy: The maintenance policy. A scenario changes this field and
            nothing else (ADR-0014).
    """

    machines: tuple[MachineConfig, ...] = field(default_factory=_reference_machines)
    buffers: tuple[BufferConfig, ...] = field(default_factory=_reference_buffers)
    arrival_interval_h: float = ARRIVAL_INTERVAL_H
    repair: RepairConfig = field(default_factory=RepairConfig)
    policy: RunToFailureConfig | ConditionBasedConfig = field(default_factory=RunToFailureConfig)

    def __post_init__(self) -> None:
        """Validate the number of machines and buffers and the arrival interval."""
        if not self.machines:
            raise ValueError("a line needs at least one machine")
        if len(self.buffers) != len(self.machines) - 1:
            raise ValueError(
                f"{len(self.machines)} machines need {len(self.machines) - 1} buffers, "
                f"got {len(self.buffers)}"
            )
        _require_positive_finite("arrival_interval_h", self.arrival_interval_h)


def reference_line_with_degradation() -> LineConfig:
    """Return the reference line with the degradation of every machine, scenario S1.

    Machine M3 degrades faster than the others (pp. 417, 420). Implements FR3.
    """
    regular = DegradationConfig(REGULAR_WEIBULL_SHAPE, REGULAR_WEIBULL_SCALE_H)
    bottleneck = DegradationConfig(M3_WEIBULL_SHAPE, M3_WEIBULL_SCALE_H)
    machines = tuple(
        MachineConfig(degradation=bottleneck if index == 2 else regular)
        for index in range(MACHINES_IN_SERIES)
    )
    return LineConfig(machines=machines)


def reference_line_condition_based(
    alarm_threshold: float,
    detection_probability: float = 1.0,
    false_alarm_probability: float = 0.0,
) -> LineConfig:
    """Return the reference line with degradation under condition-based maintenance.

    Scenario S2 varies the threshold with an ideal signal, and scenario S3 the
    two error rates. Implements FR7 and FR8.
    """
    policy = ConditionBasedConfig(
        alarm_threshold, SENSING_INTERVAL_H, detection_probability, false_alarm_probability
    )
    return dataclasses.replace(reference_line_with_degradation(), policy=policy)


@dataclass(frozen=True)
class RunConfig:
    """Length and random seed of one simulation run.

    Implements NFR1.

    Attributes:
        run_length_h: Simulated time in hours. The run covers the half-open
            interval from 0 up to but excluding this value (ADR-0008).
        seed: Root seed from which the random number streams are derived.
    """

    run_length_h: float = RUN_LENGTH_H
    seed: int = 0

    def __post_init__(self) -> None:
        """Validate the run length and the seed."""
        _require_positive_finite("run_length_h", self.run_length_h)
        if self.seed < 0:
            raise ValueError(f"seed must not be negative, got {self.seed}")
