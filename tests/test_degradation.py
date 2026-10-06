import dataclasses

import numpy as np
import simpy

from takt.config import (
    BufferConfig,
    DegradationConfig,
    LineConfig,
    MachineConfig,
    RepairConfig,
    RunConfig,
    reference_line_with_degradation,
)
from takt.model import Line, run_line, spawn_machine_streams

# A shape of 1000 makes the Weibull draw almost constant: it lies within about
# half a percent of the scale. Failure times are then predictable to within a
# few hundredths of an hour, while the draws still come from the random number
# streams of the machines.
NEARLY_CONSTANT_SHAPE = 1000.0
STEPS = 8


def nearly_constant(scale_h: float) -> DegradationConfig:
    return DegradationConfig(weibull_shape=NEARLY_CONSTANT_SHAPE, weibull_scale_h=scale_h)


def make_line(
    degradations: list[DegradationConfig | None],
    cycle_times_h: list[float] | None = None,
    capacity_parts: int = 10,
    arrival_interval_h: float = 1.0,
    maintainers: int = 3,
) -> LineConfig:
    cycles = cycle_times_h or [1.0] * len(degradations)
    return LineConfig(
        machines=tuple(
            MachineConfig(cycle_time_h=c, degradation=d)
            for c, d in zip(cycles, degradations, strict=True)
        ),
        buffers=tuple(BufferConfig(capacity_parts) for _ in degradations[1:]),
        arrival_interval_h=arrival_interval_h,
        repair=RepairConfig(maintainers=maintainers),
    )


def build(config: LineConfig, seed: int = 0) -> tuple[simpy.Environment, Line]:
    env = simpy.Environment()
    streams = spawn_machine_streams(seed, len(config.machines))
    return env, Line(env, config, streams)


def test_health_passes_through_its_nine_values_in_order():
    env, line = build(make_line([nearly_constant(1.0)]))

    env.run(until=STEPS + 1.0)

    values = [health for _, health in line.machines[0].health_trace]
    assert values == [1.0, 0.875, 0.75, 0.625, 0.5, 0.375, 0.25, 0.125, 0.0]


def test_health_is_restored_to_one_when_the_corrective_repair_ends():
    env, line = build(make_line([nearly_constant(1.0)]))

    # The repair ends at about 28 hours and the first new degradation event
    # follows one hour later.
    env.run(until=STEPS + 20.5)

    assert line.machines[0].health == 1.0
    assert line.machines[0].health_trace[-1][1] == 1.0
    assert line.maintainers.records[0].finished_at_h < STEPS + 20.5


def test_machine_without_degradation_never_fails():
    result = run_line(LineConfig(), RunConfig(run_length_h=10_080.0))

    assert result.repairs == ()
    assert result.parts_scrapped == 0


def test_failure_scraps_the_part_in_process_and_the_repair_takes_the_corrective_time():
    # The failure falls at about 4.4 hours, inside the cycle that began at 4.
    env, line = build(make_line([nearly_constant(0.55)]))

    # The repair ends at about 24.4 hours and the second failure follows at
    # about 28.8 hours, after the end of this run.
    env.run(until=27.0)

    machine = line.machines[0]
    repair = line.maintainers.records[0]
    assert machine.parts_scrapped == 1
    assert repair.started_at_h == repair.created_at_h
    assert repair.finished_at_h - repair.started_at_h == 20.0
    assert 4.3 < repair.created_at_h < 4.5


def test_failed_machine_accepts_no_further_part_until_it_is_repaired():
    env, line = build(make_line([nearly_constant(0.55)]))

    env.run(until=27.0)

    repair = line.maintainers.records[0]
    completions = line.sink.completion_times_h
    # The source waits while the machine is down, so the first part after the
    # failure enters at the end of the repair and leaves one cycle later.
    during = [t for t in completions if repair.created_at_h < t <= repair.finished_at_h]
    assert during == []
    assert completions[len([t for t in completions if t <= repair.created_at_h])] == (
        repair.finished_at_h + 1.0
    )


def test_machine_that_fails_while_starved_takes_no_part_and_scraps_none():
    # Parts are offered every 5 hours, so the machine waits for the offer at
    # 10 hours when it fails at about 8 hours.
    env, line = build(make_line([nearly_constant(1.0)], arrival_interval_h=5.0))

    env.run(until=40.0)

    machine = line.machines[0]
    repair = line.maintainers.records[0]
    assert machine.parts_scrapped == 0
    assert line.sink.completion_times_h[2] == repair.finished_at_h + 1.0


def test_machine_that_fails_while_blocked_keeps_its_finished_part():
    # A buffer of one part and a slow second machine block the first machine
    # from 7 to 11 hours, and it fails at about 8 hours (A9).
    config = make_line([nearly_constant(1.0), None], cycle_times_h=[1.0, 5.0], capacity_parts=1)
    env, line = build(config)

    env.run(until=40.0)

    assert line.machines[0].parts_scrapped == 0
    assert line.machines[0].health_trace[STEPS][1] == 0.0
    assert line.machines[0].health_trace[STEPS][0] < 9.0


def test_fourth_simultaneous_failure_waits_for_a_free_maintainer():
    config = make_line([nearly_constant(1.0)] * 4, maintainers=3)
    env, line = build(config)

    env.run(until=100.0)

    records = sorted(line.maintainers.records, key=lambda r: r.created_at_h)
    first_three, fourth = records[:3], records[3]
    assert all(r.started_at_h == r.created_at_h for r in first_three)
    assert fourth.started_at_h > fourth.created_at_h
    assert fourth.started_at_h == min(r.finished_at_h for r in first_three)
    assert fourth.finished_at_h == fourth.started_at_h + 20.0


def test_work_orders_are_served_in_the_order_of_their_creation():
    config = make_line([nearly_constant(1.0)] * 5, maintainers=1)
    env, line = build(config)

    env.run(until=150.0)

    records = line.maintainers.records
    created = [r.created_at_h for r in records]
    started = [r.started_at_h for r in records]
    assert len(records) >= 5
    assert created == sorted(created)
    assert started == sorted(started)


def test_parts_are_conserved_with_failures():
    env, line = build(reference_line_with_degradation(), seed=7)

    env.run(until=2_000.0)

    scrapped = sum(machine.parts_scrapped for machine in line.machines)
    in_line = line.source.parts_released - line.sink.parts_produced - scrapped
    held_at_most = sum(b.level_parts for b in line.buffers) + len(line.machines)
    assert scrapped > 0
    assert in_line >= sum(b.level_parts for b in line.buffers)
    assert in_line <= held_at_most


def test_two_runs_with_the_same_seed_are_identical_with_degradation():
    line_config = reference_line_with_degradation()
    run = RunConfig(run_length_h=3_000.0, seed=11)

    first = run_line(line_config, run)
    second = run_line(line_config, run)

    assert first == second
    assert len(first.repairs) > 0


def test_runs_with_different_seeds_differ_with_degradation():
    line_config = reference_line_with_degradation()

    first = run_line(line_config, RunConfig(run_length_h=3_000.0, seed=1))
    second = run_line(line_config, RunConfig(run_length_h=3_000.0, seed=2))

    assert first.repairs != second.repairs


def test_degradation_streams_of_different_machines_differ():
    streams = spawn_machine_streams(5, 3)

    draws = [s.degradation.weibull(1.5, 4) for s in streams]

    assert not np.array_equal(draws[0], draws[1])
    assert not np.array_equal(draws[1], draws[2])


def test_stream_of_a_machine_does_not_depend_on_the_number_of_machines():
    short = spawn_machine_streams(5, 2)
    long = spawn_machine_streams(5, 6)

    assert np.array_equal(short[1].degradation.weibull(1.5, 4), long[1].degradation.weibull(1.5, 4))


def test_health_history_of_a_machine_is_unchanged_when_another_machine_is_altered():
    base = reference_line_with_degradation()
    machines = list(base.machines)
    machines[2] = dataclasses.replace(machines[2], degradation=nearly_constant(50.0))
    altered = dataclasses.replace(base, machines=tuple(machines))

    env_a, line_a = build(base, seed=3)
    env_b, line_b = build(altered, seed=3)
    # Within 50 hours M1 loses health several times but at most three machines
    # can be down, so no repair of another machine delays it.
    env_a.run(until=50.0)
    env_b.run(until=50.0)

    assert line_a.machines[0].health_trace == line_b.machines[0].health_trace
    assert len(line_a.machines[0].health_trace) > 1
