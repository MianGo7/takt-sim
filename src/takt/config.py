"""Parameters of the line and of a run as immutable data.

The defaults are the serial configuration of the reference case (Dadfarnia et
al., 2023, p. 420). Every field carries its unit in its name, and the values
are validated on construction. Implements NFR4.
"""

import math
from dataclasses import dataclass, field

MACHINES_IN_SERIES = 6  # p. 420
BUFFER_CAPACITY_PARTS = 10  # p. 420
CYCLE_TIME_H = 1.0  # p. 420, derived from a path of 6 hours over 6 machines
ARRIVAL_INTERVAL_H = 1.0  # p. 420, an arrival rate of one part per hour
RUN_LENGTH_H = 10_080.0  # p. 420


def _require_positive_finite(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number, got {value}")


@dataclass(frozen=True)
class MachineConfig:
    """Parameters of one machine.

    Implements FR1.

    Attributes:
        cycle_time_h: Constant processing time of one part in hours (A3).
    """

    cycle_time_h: float = CYCLE_TIME_H

    def __post_init__(self) -> None:
        """Validate the cycle time."""
        _require_positive_finite("cycle_time_h", self.cycle_time_h)


@dataclass(frozen=True)
class BufferConfig:
    """Parameters of one buffer.

    Implements FR2.

    Attributes:
        capacity_parts: Number of parts the buffer holds, at least one. A
            capacity of zero is a rendezvous between two machines and is not
            supported before B5.
    """

    capacity_parts: int = BUFFER_CAPACITY_PARTS

    def __post_init__(self) -> None:
        """Validate the capacity."""
        if self.capacity_parts < 1:
            raise ValueError(f"capacity_parts must be at least 1, got {self.capacity_parts}")


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
    """

    machines: tuple[MachineConfig, ...] = field(default_factory=_reference_machines)
    buffers: tuple[BufferConfig, ...] = field(default_factory=_reference_buffers)
    arrival_interval_h: float = ARRIVAL_INTERVAL_H

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
