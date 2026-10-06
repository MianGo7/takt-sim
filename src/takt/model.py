"""Simulation of the serial line without degradation.

Contains the source, the machines, the buffers, and the sink as SimPy
processes. Blocking and starvation are not coded as states: they follow from
the limited capacity of the buffers.
"""

from collections.abc import Generator, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import simpy

from takt.config import BufferConfig, LineConfig, MachineConfig, RunConfig

type Steps = Iterator[simpy.Event]
type Taking = Generator[simpy.Event, Any, Part]


@dataclass(frozen=True)
class Part:
    """A part that moves through the line.

    Attributes:
        identifier: Running number in the order of entry.
        entered_at_h: Time in hours at which the part entered the first machine.
    """

    identifier: int
    entered_at_h: float


class PartSupplier(Protocol):
    """Something a machine takes its next part from."""

    def take(self) -> Taking:
        """Wait until a part is available and return it."""
        ...


class PartReceiver(Protocol):
    """Something a machine hands its finished part to."""

    def accept(self, part: Part) -> Steps:
        """Wait until the part has been taken over."""
        ...


class Source:
    """Offers raw parts at a fixed interval to the first machine.

    The first part is offered at time zero. The next offer follows one
    interval after the previous part was taken, so that the source waits
    instead of losing parts when the first machine cannot accept (A7).
    Implements FR1.
    """

    def __init__(self, env: simpy.Environment, arrival_interval_h: float) -> None:
        """Create a source that offers its first part at time zero."""
        self._env = env
        self._interval_h = arrival_interval_h
        self._next_offer_h = 0.0
        self.parts_released = 0

    def take(self) -> Taking:
        """Wait for the next offer and hand the part to the caller."""
        wait_h = self._next_offer_h - self._env.now
        if wait_h > 0:
            yield self._env.timeout(wait_h)
        self._next_offer_h = self._env.now + self._interval_h
        part = Part(self.parts_released, self._env.now)
        self.parts_released += 1
        return part


class Buffer:
    """Holds waiting parts between two machines up to its capacity.

    Implements FR2.
    """

    def __init__(self, env: simpy.Environment, config: BufferConfig) -> None:
        """Create an empty buffer."""
        self.capacity_parts = config.capacity_parts
        self._store = simpy.Store(env, capacity=config.capacity_parts)

    @property
    def level_parts(self) -> int:
        """Number of parts currently waiting."""
        return len(self._store.items)

    def take(self) -> Taking:
        """Wait until a part is waiting and return the oldest one."""
        part = yield self._store.get()
        return part

    def accept(self, part: Part) -> Steps:
        """Wait until the buffer has a free place and store the part."""
        yield self._store.put(part)


class Sink:
    """Collects the finished parts and the times at which they arrived.

    Implements FR1.
    """

    def __init__(self, env: simpy.Environment) -> None:
        """Create an empty sink."""
        self._env = env
        self.completion_times_h: list[float] = []

    @property
    def parts_produced(self) -> int:
        """Number of parts that reached the sink."""
        return len(self.completion_times_h)

    def accept(self, part: Part) -> Steps:
        """Record the arrival of a finished part."""
        self.completion_times_h.append(self._env.now)
        return iter(())


class Machine:
    """Processes one part at a time with a constant cycle time.

    A machine that cannot hand over its finished part holds it and is blocked,
    and a machine without a part waits and is starved. Implements FR1 and FR2.
    """

    def __init__(
        self,
        env: simpy.Environment,
        name: str,
        config: MachineConfig,
        inbound: PartSupplier,
        outbound: PartReceiver,
        rng: np.random.Generator,
    ) -> None:
        """Create the machine and start its process."""
        self.name = name
        self.cycle_time_h = config.cycle_time_h
        # ADR-0009: the generator is created now and drawn from from B3 on,
        # so that adding the degradation does not shift any other stream.
        self.rng = rng
        self._env = env
        self._inbound = inbound
        self._outbound = outbound
        env.process(self._run())

    def _run(self) -> Steps:
        while True:
            part = yield from self._inbound.take()
            yield self._env.timeout(self.cycle_time_h)
            yield from self._outbound.accept(part)


def spawn_machine_streams(seed: int, count: int) -> list[np.random.Generator]:
    """Derive one independent random number generator per machine from a seed.

    Implements NFR1.
    """
    return [np.random.default_rng(child) for child in np.random.SeedSequence(seed).spawn(count)]


class Line:
    """The assembled line of source, machines, buffers, and sink.

    Implements FR1 and FR2.
    """

    def __init__(
        self,
        env: simpy.Environment,
        config: LineConfig,
        streams: Sequence[np.random.Generator],
    ) -> None:
        """Build the line and start the processes of all machines."""
        if len(streams) != len(config.machines):
            raise ValueError(
                f"{len(config.machines)} machines need one stream each, got {len(streams)}"
            )
        self.source = Source(env, config.arrival_interval_h)
        self.sink = Sink(env)
        self.buffers = [Buffer(env, buffer) for buffer in config.buffers]
        suppliers: list[PartSupplier] = [self.source, *self.buffers]
        receivers: list[PartReceiver] = [*self.buffers, self.sink]
        self.machines = [
            Machine(env, f"M{index + 1}", machine, inbound, outbound, rng)
            for index, (machine, inbound, outbound, rng) in enumerate(
                zip(config.machines, suppliers, receivers, streams, strict=True)
            )
        ]


@dataclass(frozen=True)
class LineResult:
    """Output of one run.

    Attributes:
        parts_produced: Parts that reached the sink before the end of the run.
        completion_times_h: Arrival time of each produced part in hours.
    """

    parts_produced: int
    completion_times_h: tuple[float, ...]


def run_line(line_config: LineConfig, run_config: RunConfig) -> LineResult:
    """Simulate the line for the run length and return its output.

    Parts still inside the line at the end of the run are not counted
    (ADR-0008). Implements NFR1.
    """
    env = simpy.Environment()
    streams = spawn_machine_streams(run_config.seed, len(line_config.machines))
    line = Line(env, line_config, streams)
    env.run(until=run_config.run_length_h)
    return LineResult(line.sink.parts_produced, tuple(line.sink.completion_times_h))
