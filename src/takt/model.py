"""Simulation of the serial line with degradation and corrective repair.

Contains the source, the machines, the buffers, the sink, and the maintainers
as SimPy processes. Blocking and starvation are not coded as states: they
follow from the limited capacity of the buffers.
"""

import contextlib
from collections import deque
from collections.abc import Callable, Generator, Iterator, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Protocol

import numpy as np
import simpy

from takt.config import (
    HEALTH_STEPS,
    BufferConfig,
    ConditionBasedConfig,
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


class Handoff:
    """A buffer of capacity zero: a machine hands over only to a waiting machine.

    The giving machine holds its finished part and is blocked until the
    receiving machine asks for a part. Nothing waits in the link, so its level
    is always zero. Implements FR2.
    """

    capacity_parts = 0

    def __init__(self, env: simpy.Environment) -> None:
        """Create a link with no waiting machine on either side."""
        self.level_trace: list[tuple[float, int]] = [(env.now, 0)]
        self._env = env
        self._takers: deque[simpy.Event] = deque()
        self._givers: deque[tuple[Part, simpy.Event]] = deque()

    @property
    def level_parts(self) -> int:
        """Number of parts currently waiting, always zero."""
        return 0

    def take(self) -> Taking:
        """Wait until the giving machine offers a part and return it."""
        arrival = self._env.event()
        if self._givers:
            part, released = self._givers.popleft()
            released.succeed()
            arrival.succeed(part)
        else:
            self._takers.append(arrival)
        try:
            part = yield arrival
        except simpy.Interrupt:
            # The same rule as for the buffer: a part that is already handed
            # over belongs to the caller, otherwise the wait is withdrawn.
            if not arrival.triggered:
                self._takers.remove(arrival)
                raise
            return arrival.value
        return part

    def accept(self, part: Part) -> Steps:
        """Wait until the receiving machine has taken the part."""
        released = self._env.event()
        if self._takers:
            self._takers.popleft().succeed(part)
            released.succeed()
        else:
            self._givers.append((part, released))
        yield released


type Link = Buffer | Handoff


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
        degradation: Draws the times between two degradation events.
        sensor: Draws the outcome of every reading of the monitoring system.
            One value is drawn per reading whatever the outcome, so that the
            stream does not depend on the policy or on the health (ADR-0014).
    """

    degradation: np.random.Generator
    sensor: np.random.Generator


class RepairKind(Enum):
    """Whether a repair restores a failed machine or one that was still working."""

    CORRECTIVE = "corrective"
    PREVENTIVE = "preventive"


@dataclass(frozen=True)
class RepairRecord:
    """One completed repair as recorded by the maintainers.

    Attributes:
        machine: Name of the repaired machine.
        kind: Corrective if the machine had failed when the repair began.
        created_at_h: Time in hours at which the work order was created.
        started_at_h: Time in hours at which a maintainer began the repair.
        finished_at_h: Time in hours at which the machine was restored.
    """

    machine: str
    kind: RepairKind
    created_at_h: float
    started_at_h: float
    finished_at_h: float


class Maintainers:
    """A pool of maintainers that serves work orders in the order of creation.

    The queue of the SimPy resource is first in, first out, which is the
    reading of the reference case in A8. Implements FR5 and FR6.
    """

    def __init__(self, env: simpy.Environment, config: RepairConfig) -> None:
        """Create the pool."""
        self._env = env
        self._resource = simpy.Resource(env, capacity=config.maintainers)
        self._config = config
        self.records: list[RepairRecord] = []

    def repair_time_h(self, health: float) -> float:
        """Return the duration of a repair that starts at the given health (FR6)."""
        return self._config.repair_time_h(health)

    def repair(
        self,
        machine: str,
        begin: Callable[[], tuple[float, RepairKind]],
        end: Callable[[], None],
    ) -> Steps:
        """Wait for a free maintainer, repair the machine, and record the repair.

        `begin` is called when the maintainer arrives and returns the duration
        and the kind, which depend on the health at that moment. `end` is called
        when the repair is complete.
        """
        created_at_h = self._env.now
        with self._resource.request() as maintainer:
            yield maintainer
            started_at_h = self._env.now
            duration_h, kind = begin()
            yield self._env.timeout(duration_h)
            end()
        self.records.append(RepairRecord(machine, kind, created_at_h, started_at_h, self._env.now))


class Machine:
    """Processes one part at a time, degrades, and is repaired.

    A machine that cannot hand over its finished part holds it and is blocked,
    and a machine without a part waits and is starved. The health is held as
    a number of remaining steps, so that it is exact (ADR-0010).
    A failure scraps the part in process. A preventive repair
    pauses the part in process and scraps nothing (A11). In both cases the
    machine takes no further part until the repair has ended. A machine has at
    most one open work order (A12). Implements FR1 to FR7.
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
        self.failures: list[tuple[float, MachineState]] = []
        self.health_trace: list[tuple[float, float]] = [(env.now, 1.0)]
        self.state_trace: list[tuple[float, MachineState]] = [(env.now, MachineState.STARVED)]
        self._degradation = config.degradation
        self._streams = streams
        self._remaining_steps = HEALTH_STEPS
        self._failed = False
        self._order_open = False
        self._restored: simpy.Event | None = None
        self._interruptible = False
        self._holding = False
        self._blocked = False
        self._env = env
        self._inbound = inbound
        self._outbound = outbound
        self._maintainers = maintainers
        self._process = env.process(self._run())
        self._lifecycle = env.process(self._degrade()) if config.degradation is not None else None

    @property
    def health(self) -> float:
        """Health between 0 and 1, exact because the step is a power of two."""
        return self._remaining_steps / HEALTH_STEPS

    @property
    def parts_scrapped(self) -> int:
        """Number of parts scrapped by failures of this machine."""
        return len(self.scrap_times_h)

    @property
    def holding_part(self) -> bool:
        """Whether a part is in process or finished and waiting to be handed over."""
        return self._holding

    @property
    def failed(self) -> bool:
        """Whether the machine has failed and is not yet restored."""
        return self._failed

    @property
    def work_order_open(self) -> bool:
        """Whether a work order of this machine is waiting or being served."""
        return self._order_open

    def request_repair(self) -> bool:
        """Create a work order unless one is open and report whether one was created.

        Implements FR7.
        """
        if self._order_open:
            return False
        self._order_open = True
        self._env.process(self._maintainers.repair(self.name, self._begin_repair, self._end_repair))
        return True

    def _set_state(self, state: MachineState) -> None:
        # An interval of length zero carries no time share, so a state that
        # is replaced within the same instant is dropped from the trace.
        now = self._env.now
        if self.state_trace[-1][0] == now:
            self.state_trace.pop()
        if self.state_trace and self.state_trace[-1][1] is state:
            return
        self.state_trace.append((now, state))

    def _set_working_state(self, state: MachineState) -> None:
        # A9: a machine that is down and still hands over a finished part keeps
        # its down state in the record.
        if self._restored is None:
            self._set_state(state)

    def _scrap(self) -> None:
        self.scrap_times_h.append(self._env.now)
        self._holding = False

    def _run(self) -> Steps:
        part: Part | None = None
        remaining_h = 0.0
        while True:
            while self._restored is not None:
                yield self._restored
            if part is None:
                self._set_working_state(MachineState.STARVED)
                self._interruptible = True
                # A failure or a repair has set the flags that follow.
                with contextlib.suppress(simpy.Interrupt):
                    part = yield from self._inbound.take()
                self._interruptible = False
                if part is not None:
                    self._holding = True
                    remaining_h = self.cycle_time_h
                    if self._failed:
                        # ADR-0010: a part handed over at the instant of the
                        # failure is scrapped, so that no part is lost unseen.
                        self._scrap()
                        part = None
                if part is None or self._restored is not None:
                    continue
            self._set_working_state(MachineState.PROCESSING)
            started_h = self._env.now
            self._interruptible = True
            try:
                yield self._env.timeout(remaining_h)
                remaining_h = 0.0
            except simpy.Interrupt:
                remaining_h -= self._env.now - started_h
            self._interruptible = False
            if self._failed:
                # ADR-0010: only a part in process is scrapped. A machine
                # that was starved took no part and has nothing to scrap.
                self._scrap()
                part = None
                continue
            if remaining_h > 0.0:
                continue  # A11: paused by a preventive repair, resumed afterwards.
            # A10: the share is added when the cycle completes, with the
            # health at that moment.
            finished = replace(part, health_sum=part.health_sum + self.health)
            part = None
            self._set_working_state(MachineState.BLOCKED)
            self._blocked = True
            yield from self._outbound.accept(finished)
            self._blocked = False
            self._holding = False

    def _degrade(self) -> Steps:
        assert self._degradation is not None
        shape = self._degradation.weibull_shape
        scale_h = self._degradation.weibull_scale_h
        while True:
            try:
                while self._remaining_steps > 0:
                    yield self._env.timeout(scale_h * self._streams.degradation.weibull(shape))
                    self._remaining_steps -= 1
                    self.health_trace.append((self._env.now, self.health))
                self._fail()
            except simpy.Interrupt:
                pass  # A preventive repair has begun, the degradation stops.
            while self._restored is not None:
                yield self._restored

    def _fail(self) -> None:
        self.failures.append((self._env.now, self.state_trace[-1][1]))
        self._failed = True
        self._restored = self._env.event()
        self._set_state(MachineState.AWAITING_REPAIR)
        # ADR-0010: a machine that is blocked holds a finished part and is
        # not interrupted, it fails after handing the part over.
        if self._interruptible:
            self._process.interrupt()
        # A12: a work order that is already waiting serves the failure.
        self.request_repair()

    def _begin_repair(self) -> tuple[float, RepairKind]:
        """Start the repair that the health at this moment calls for (FR6)."""
        duration_h = self._maintainers.repair_time_h(self.health)
        if self._failed:
            self._set_state(MachineState.UNDER_REPAIR)
            return duration_h, RepairKind.CORRECTIVE
        self._restored = self._env.event()
        self._set_state(MachineState.UNDER_REPAIR)
        if self._interruptible:
            self._process.interrupt()
        if self._lifecycle is not None:
            self._lifecycle.interrupt()
        return duration_h, RepairKind.PREVENTIVE

    def _end_repair(self) -> None:
        self._remaining_steps = HEALTH_STEPS
        self.health_trace.append((self._env.now, self.health))
        self._failed = False
        self._order_open = False
        if self._blocked:
            # A9: the machine still holds its finished part, so after the
            # repair it is blocked and not starved.
            self._set_state(MachineState.BLOCKED)
        restored, self._restored = self._restored, None
        assert restored is not None
        restored.succeed()


@dataclass(frozen=True)
class Alarm:
    """An alarm of the monitoring system that created a work order.

    Attributes:
        time_h: Time in hours of the reading.
        machine: Name of the machine.
        health: Health that the machine had at the reading.
        true_alarm: Whether the health was at or below the alarm threshold. An
            alarm above the threshold is a false alarm.
    """

    time_h: float
    machine: str
    health: float
    true_alarm: bool


class MaintenancePolicy(Protocol):
    """The part of the model that decides when a work order is created.

    A scenario exchanges the policy and nothing else (ADR-0014).
    """

    alarms: list[Alarm]

    def start(self) -> None:
        """Start the processes of the policy, if it has any."""
        ...


class RunToFailure:
    """Creates no work order of its own: a machine is repaired when it fails.

    Implements FR4.
    """

    def __init__(self) -> None:
        """Create the policy."""
        self.alarms: list[Alarm] = []

    def start(self) -> None:
        """Do nothing, the failure of a machine creates its work order."""


class ConditionBased:
    """Reads the health of every machine at a fixed interval and raises alarms.

    A reading at or below the threshold raises an alarm with the detection
    probability, and a reading above it raises a false alarm with the false
    alarm probability. An alarm creates a work order unless the machine has one
    open (A12). The first reading is one interval after the start. Implements
    FR7 and FR8.
    """

    def __init__(
        self,
        env: simpy.Environment,
        config: ConditionBasedConfig,
        machines: Sequence[Machine],
        streams: Sequence[MachineStreams],
    ) -> None:
        """Create the monitoring system for the machines and their sensor streams."""
        self.alarms: list[Alarm] = []
        self._env = env
        self._config = config
        self._machines = machines
        self._streams = streams

    def start(self) -> None:
        """Start the process that reads the machines."""
        self._env.process(self._sense())

    def _sense(self) -> Steps:
        config = self._config
        while True:
            yield self._env.timeout(config.sensing_interval_h)
            for machine, streams in zip(self._machines, self._streams, strict=True):
                draw = streams.sensor.random()
                health = machine.health
                true_alarm = health <= config.alarm_threshold
                probability = (
                    config.detection_probability if true_alarm else config.false_alarm_probability
                )
                if draw < probability and machine.request_repair():
                    self.alarms.append(Alarm(self._env.now, machine.name, health, true_alarm))


def spawn_machine_streams(seed: int, count: int) -> list[MachineStreams]:
    """Derive the independent random number streams of every machine from a seed.

    The streams of a machine depend on the seed and its position only, not on
    the number of machines, and the degradation stream does not depend on the
    sensor stream (ADR-0010, ADR-0014). Implements NFR1.
    """
    streams = []
    for child in np.random.SeedSequence(seed).spawn(count):
        degradation, sensor = child.spawn(2)
        streams.append(
            MachineStreams(np.random.default_rng(degradation), np.random.default_rng(sensor))
        )
    return streams


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
        self.buffers: list[Link] = [
            Handoff(env) if buffer.capacity_parts == 0 else Buffer(env, buffer)
            for buffer in config.buffers
        ]
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
        self.policy: MaintenancePolicy = (
            ConditionBased(env, config.policy, self.machines, streams)
            if isinstance(config.policy, ConditionBasedConfig)
            else RunToFailure()
        )
        self.policy.start()


@dataclass(frozen=True)
class LineResult:
    """Raw output of one run, from which the indicators are derived.

    The traces carry the time of every change, so that the experiment can
    cut any window out of them without rerunning the model.

    Attributes:
        parts: The parts that reached the sink before the end of the run.
        scrap_times_h: Time of every scrapped part in hours, per machine.
        repairs: The completed repairs in the order of their completion.
        failures: Per machine the time of every failure with the state the
            machine was in.
        alarms: The alarms that created a work order.
        buffer_level_traces: Per buffer the pairs of time and level, with the
            level held until the next pair.
        machine_state_traces: Per machine the pairs of time and state, with
            the state held until the next pair.
        run_length_h: Length of the run in hours.
    """

    parts: tuple[CompletedPart, ...]
    scrap_times_h: tuple[tuple[float, ...], ...]
    repairs: tuple[RepairRecord, ...]
    failures: tuple[tuple[tuple[float, MachineState], ...], ...]
    alarms: tuple[Alarm, ...]
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
        failures=tuple(tuple(machine.failures) for machine in line.machines),
        alarms=tuple(line.policy.alarms),
        buffer_level_traces=tuple(tuple(buffer.level_trace) for buffer in line.buffers),
        machine_state_traces=tuple(tuple(machine.state_trace) for machine in line.machines),
        run_length_h=run_config.run_length_h,
    )
