"""Simulation of the serial line with degradation and corrective repair.

Contains the source, the machines, the buffers, the sink, and the maintainers
as SimPy processes. Blocking and starvation are not coded as states: they
follow from the limited capacity of the buffers.
"""

from collections.abc import Callable, Generator, Iterator, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Protocol

import numpy as np
import simpy

from takt.config import (
    HEALTH_STEPS,
    BufferConfig,
    LineConfig,
    MachineConfig,
    RepairConfig,
    RunConfig,
)

type Steps = Iterator[simpy.Event]
type Taking = Generator[simpy.Event, Any, Part]


@dataclass(frozen=True)
class Part:
    """A part that moves through the line.

    Attributes:
        identifier: Running number in the order of entry.
        entered_at_h: Time in hours at which the part entered the first machine.
        health_sum: Sum of the health values that the machines had when they
            finished the part. The quality is this sum divided by the number
            of machines (A10), which is exact for a healthy line.
    """

    identifier: int
    entered_at_h: float
    health_sum: float = 0.0


@dataclass(frozen=True)
class CompletedPart:
    """A part that reached the sink, as recorded for the indicators.

    Attributes:
        completed_at_h: Time in hours at which the part reached the sink.
        lead_time_h: Time in hours from entering the first machine to the sink.
        quality: Product quality between 0 and 1. Implements FR9.
    """

    completed_at_h: float
    lead_time_h: float
    quality: float


class MachineState(Enum):
    """What a machine is doing, as recorded for the time shares.

    A machine that is failed and still hands over a finished part is recorded
    as awaiting repair (A9).
    """

    PROCESSING = "processing"
    STARVED = "starved"
    BLOCKED = "blocked"
    AWAITING_REPAIR = "awaiting_repair"
    UNDER_REPAIR = "under_repair"


class PartSupplier(Protocol):
    """Something a machine takes its next part from."""

    def take(self) -> Taking:
        """Wait until a part is available and return it.

        The wait can be interrupted, and an interrupted wait takes no part.
        """
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
        self.level_trace: list[tuple[float, int]] = [(env.now, 0)]
        self._env = env
        self._store = simpy.Store(env, capacity=config.capacity_parts)

    @property
    def level_parts(self) -> int:
        """Number of parts currently waiting."""
        return len(self._store.items)

    def _record_level(self) -> None:
        # Every change of the level is followed by the resumption of the
        # process that caused it, so the last record of an instant is final.
        now = self._env.now
        level = self.level_parts
        if self.level_trace[-1][0] == now:
            self.level_trace.pop()
        if self.level_trace and self.level_trace[-1][1] == level:
            return
        self.level_trace.append((now, level))

    def take(self) -> Taking:
        """Wait until a part is waiting and return the oldest one."""
        request = self._store.get()
        try:
            part = yield request
        except simpy.Interrupt:
            # A part that is already handed over belongs to the caller, who
            # checks for the failure that caused the interrupt. Otherwise the
            # request is withdrawn, so that it does not take a part later.
            if not request.triggered:
                request.cancel()
                raise
            self._record_level()
            return request.value
        self._record_level()
        return part

    def accept(self, part: Part) -> Steps:
        """Wait until the buffer has a free place and store the part."""
        yield self._store.put(part)
        self._record_level()


class Sink:
    """Collects the finished parts with their lead time and quality.

    Implements FR1 and FR9.
    """

    def __init__(self, env: simpy.Environment, machine_count: int) -> None:
        """Create an empty sink for a line of the given number of machines."""
        self._env = env
        self._machine_count = machine_count
        self.parts: list[CompletedPart] = []

    @property
    def parts_produced(self) -> int:
        """Number of parts that reached the sink."""
        return len(self.parts)

    @property
    def completion_times_h(self) -> list[float]:
        """Arrival time of each part in hours."""
        return [part.completed_at_h for part in self.parts]

    def accept(self, part: Part) -> Steps:
        """Record the arrival of a finished part."""
        now = self._env.now
        self.parts.append(
            CompletedPart(now, now - part.entered_at_h, part.health_sum / self._machine_count)
        )
        return iter(())


@dataclass(frozen=True)
class MachineStreams:
    """The independent random number generators of one machine.

    Attributes:
        degradation: Draws the times between two degradation events. A stream
            for the sensor errors is added in B6.
    """

    degradation: np.random.Generator


@dataclass(frozen=True)
class RepairRecord:
    """One completed repair as recorded by the maintainers.

    Attributes:
        machine: Name of the repaired machine.
        created_at_h: Time in hours at which the work order was created.
        started_at_h: Time in hours at which a maintainer began the repair.
        finished_at_h: Time in hours at which the machine was restored.
    """

    machine: str
    created_at_h: float
    started_at_h: float
    finished_at_h: float


class Maintainers:
    """A pool of maintainers that serves work orders in the order of creation.

    The queue of the SimPy resource is first in, first out, which is the
    reading of the reference case in A8. Implements FR4 and FR5.
    """

    def __init__(self, env: simpy.Environment, config: RepairConfig) -> None:
        """Create the pool."""
        self._env = env
        self._resource = simpy.Resource(env, capacity=config.maintainers)
        self._corrective_repair_time_h = config.corrective_repair_time_h
        self.records: list[RepairRecord] = []

    def corrective_repair(self, machine: str, on_start: Callable[[], None]) -> Steps:
        """Wait for a free maintainer, call `on_start`, and repair the named machine."""
        created_at_h = self._env.now
        with self._resource.request() as maintainer:
            yield maintainer
            started_at_h = self._env.now
            on_start()
            yield self._env.timeout(self._corrective_repair_time_h)
        self.records.append(RepairRecord(machine, created_at_h, started_at_h, self._env.now))


class Machine:
    """Processes one part at a time and degrades until it fails.

    A machine that cannot hand over its finished part holds it and is blocked,
    and a machine without a part waits and is starved. The health is held as
    a number of remaining steps, so that it is exact (ADR-0010).
    A failure scraps the part in process and keeps the machine
    from taking another one until the corrective repair has ended. Implements
    FR1 to FR4.
    """

    def __init__(
        self,
        env: simpy.Environment,
        name: str,
        config: MachineConfig,
        inbound: PartSupplier,
        outbound: PartReceiver,
        streams: MachineStreams,
        maintainers: Maintainers,
    ) -> None:
        """Create the machine and start its processes."""
        self.name = name
        self.cycle_time_h = config.cycle_time_h
        self.scrap_times_h: list[float] = []
        self.health_trace: list[tuple[float, float]] = [(env.now, 1.0)]
        self.state_trace: list[tuple[float, MachineState]] = [(env.now, MachineState.STARVED)]
        self._degradation = config.degradation
        self._streams = streams
        self._remaining_steps = HEALTH_STEPS
        self._failed = False
        self._restored: simpy.Event | None = None
        self._interruptible = False
        self._env = env
        self._inbound = inbound
        self._outbound = outbound
        self._maintainers = maintainers
        self._process = env.process(self._run())
        if config.degradation is not None:
            env.process(self._degrade())

    @property
    def health(self) -> float:
        """Health between 0 and 1, exact because the step is a power of two."""
        return self._remaining_steps / HEALTH_STEPS

    @property
    def parts_scrapped(self) -> int:
        """Number of parts scrapped by failures of this machine."""
        return len(self.scrap_times_h)

    @property
    def failed(self) -> bool:
        """Whether the machine waits for or undergoes its corrective repair."""
        return self._failed

    def _set_state(self, state: MachineState) -> None:
        # An interval of length zero carries no time share, so a state that
        # is replaced within the same instant is dropped from the trace.
        now = self._env.now
        if self.state_trace[-1][0] == now:
            self.state_trace.pop()
        if self.state_trace and self.state_trace[-1][1] is state:
            return
        self.state_trace.append((now, state))

    def _run(self) -> Steps:
        while True:
            if self._restored is not None:
                yield self._restored
            self._set_state(MachineState.STARVED)
            part: Part | None = None
            self._interruptible = True
            try:
                part = yield from self._inbound.take()
                if not self._failed:
                    self._set_state(MachineState.PROCESSING)
                yield self._env.timeout(self.cycle_time_h)
            except simpy.Interrupt:
                pass  # The failure that caused it has set the failed flag.
            self._interruptible = False
            if self._failed:
                # ADR-0010: only a part in process is scrapped. A machine
                # that was starved took no part and has nothing to scrap.
                if part is not None:
                    self.scrap_times_h.append(self._env.now)
                continue
            assert part is not None
            # A10: the share is added when the cycle completes, with the
            # health at that moment.
            part = replace(part, health_sum=part.health_sum + self.health)
            self._set_state(MachineState.BLOCKED)
            yield from self._outbound.accept(part)

    def _degrade(self) -> Steps:
        assert self._degradation is not None
        shape = self._degradation.weibull_shape
        scale_h = self._degradation.weibull_scale_h
        while True:
            while self._remaining_steps > 0:
                yield self._env.timeout(scale_h * self._streams.degradation.weibull(shape))
                self._remaining_steps -= 1
                self.health_trace.append((self._env.now, self.health))
            self._fail()
            yield from self._maintainers.corrective_repair(
                self.name, lambda: self._set_state(MachineState.UNDER_REPAIR)
            )
            self._remaining_steps = HEALTH_STEPS
            self.health_trace.append((self._env.now, self.health))
            self._failed = False
            restored, self._restored = self._restored, None
            assert restored is not None
            restored.succeed()

    def _fail(self) -> None:
        self._failed = True
        self._restored = self._env.event()
        self._set_state(MachineState.AWAITING_REPAIR)
        # ADR-0010: a machine that is blocked holds a finished part and is
        # not interrupted, it fails after handing the part over.
        if self._interruptible:
            self._process.interrupt()


def spawn_machine_streams(seed: int, count: int) -> list[MachineStreams]:
    """Derive the independent random number streams of every machine from a seed.

    The stream of a machine depends on the seed and its position only, not on
    the number of machines (ADR-0010). Implements NFR1.
    """
    return [
        MachineStreams(degradation=np.random.default_rng(child.spawn(1)[0]))
        for child in np.random.SeedSequence(seed).spawn(count)
    ]


class Line:
    """The assembled line of source, machines, buffers, and sink.

    Implements FR1 and FR2.
    """

    def __init__(
        self,
        env: simpy.Environment,
        config: LineConfig,
        streams: Sequence[MachineStreams],
    ) -> None:
        """Build the line and start the processes of all machines."""
        if len(streams) != len(config.machines):
            raise ValueError(
                f"{len(config.machines)} machines need one stream each, got {len(streams)}"
            )
        self.source = Source(env, config.arrival_interval_h)
        self.sink = Sink(env, len(config.machines))
        self.buffers = [Buffer(env, buffer) for buffer in config.buffers]
        self.maintainers = Maintainers(env, config.repair)
        suppliers: list[PartSupplier] = [self.source, *self.buffers]
        receivers: list[PartReceiver] = [*self.buffers, self.sink]
        self.machines = [
            Machine(
                env, f"M{index + 1}", machine, inbound, outbound, machine_streams, self.maintainers
            )
            for index, (machine, inbound, outbound, machine_streams) in enumerate(
                zip(config.machines, suppliers, receivers, streams, strict=True)
            )
        ]


@dataclass(frozen=True)
class LineResult:
    """Raw output of one run, from which the indicators are derived.

    The traces carry the time of every change, so that the experiment can
    cut any window out of them without rerunning the model.

    Attributes:
        parts: The parts that reached the sink before the end of the run.
        scrap_times_h: Time of every scrapped part in hours, per machine.
        repairs: The completed repairs in the order of their completion.
        buffer_level_traces: Per buffer the pairs of time and level, with the
            level held until the next pair.
        machine_state_traces: Per machine the pairs of time and state, with
            the state held until the next pair.
        run_length_h: Length of the run in hours.
    """

    parts: tuple[CompletedPart, ...]
    scrap_times_h: tuple[tuple[float, ...], ...]
    repairs: tuple[RepairRecord, ...]
    buffer_level_traces: tuple[tuple[tuple[float, int], ...], ...]
    machine_state_traces: tuple[tuple[tuple[float, MachineState], ...], ...]
    run_length_h: float

    @property
    def parts_produced(self) -> int:
        """Number of parts that reached the sink."""
        return len(self.parts)

    @property
    def completion_times_h(self) -> tuple[float, ...]:
        """Arrival time of each produced part in hours."""
        return tuple(part.completed_at_h for part in self.parts)

    @property
    def parts_scrapped(self) -> int:
        """Parts scrapped by a failure of a machine."""
        return sum(len(times) for times in self.scrap_times_h)


def run_line(line_config: LineConfig, run_config: RunConfig) -> LineResult:
    """Simulate the line for the run length and return its raw output.

    Parts still inside the line at the end of the run are not counted
    (ADR-0008). Implements NFR1.
    """
    env = simpy.Environment()
    streams = spawn_machine_streams(run_config.seed, len(line_config.machines))
    line = Line(env, line_config, streams)
    env.run(until=run_config.run_length_h)
    return LineResult(
        parts=tuple(line.sink.parts),
        scrap_times_h=tuple(tuple(machine.scrap_times_h) for machine in line.machines),
        repairs=tuple(line.maintainers.records),
        buffer_level_traces=tuple(tuple(buffer.level_trace) for buffer in line.buffers),
        machine_state_traces=tuple(tuple(machine.state_trace) for machine in line.machines),
        run_length_h=run_config.run_length_h,
    )
