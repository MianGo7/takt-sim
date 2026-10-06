import numpy as np
import simpy

from takt.config import BufferConfig, LineConfig, MachineConfig, RunConfig
from takt.model import Line, run_line, spawn_machine_streams


def make_line(
    cycle_times_h: list[float],
    capacity_parts: int = 10,
    arrival_interval_h: float = 1.0,
) -> LineConfig:
    return LineConfig(
        machines=tuple(MachineConfig(cycle_time_h=c) for c in cycle_times_h),
        buffers=tuple(BufferConfig(capacity_parts) for _ in cycle_times_h[1:]),
        arrival_interval_h=arrival_interval_h,
    )


def build(config: LineConfig) -> tuple[simpy.Environment, Line]:
    env = simpy.Environment()
    streams = spawn_machine_streams(0, len(config.machines))
    return env, Line(env, config, streams)


def test_reference_line_produces_one_part_per_hour_after_filling_the_line():
    result = run_line(LineConfig(), RunConfig(run_length_h=10_080.0))

    assert result.parts_produced == 10_074


def test_first_part_reaches_the_sink_after_the_sum_of_the_cycle_times():
    result = run_line(LineConfig(), RunConfig(run_length_h=7.0))

    assert result.completion_times_h == (6.0,)


def test_part_that_arrives_exactly_at_the_end_of_the_run_is_not_counted():
    result = run_line(LineConfig(), RunConfig(run_length_h=6.0))

    assert result.parts_produced == 0


def test_single_machine_produces_one_part_per_cycle():
    result = run_line(make_line([2.0], arrival_interval_h=1.0), RunConfig(run_length_h=10.5))

    assert result.completion_times_h == (2.0, 4.0, 6.0, 8.0, 10.0)


def test_slow_last_machine_fills_the_buffer_and_blocks_the_machine_before_it():
    config = make_line([1.0, 2.0], capacity_parts=2)
    env, line = build(config)

    env.run(until=100.0)

    # The first machine holds its finished part, two parts wait in the buffer,
    # and the second machine is processing one.
    assert line.buffers[0].level_parts == 2
    assert line.source.parts_released - line.sink.parts_produced == 4
    assert line.sink.completion_times_h[-3:] == [95.0, 97.0, 99.0]


def test_slow_first_machine_leaves_the_following_machine_starved():
    config = make_line([2.0, 1.0])
    env, line = build(config)
    levels: list[int] = []

    def monitor(env: simpy.Environment):
        while True:
            levels.append(line.buffers[0].level_parts)
            yield env.timeout(0.25)

    env.process(monitor(env))

    env.run(until=50.0)

    # Every part leaves the buffer at the moment it arrives, so the buffer
    # is empty whenever the second machine waits.
    assert max(levels) == 1
    assert line.sink.completion_times_h[:3] == [3.0, 5.0, 7.0]
    assert line.sink.completion_times_h[-1] == 49.0


def test_slow_source_starves_the_whole_line():
    result = run_line(make_line([1.0, 1.0], arrival_interval_h=2.0), RunConfig(run_length_h=11.0))

    assert result.completion_times_h == (2.0, 4.0, 6.0, 8.0, 10.0)


def test_output_of_a_line_is_limited_by_its_slowest_machine():
    config = make_line([1.0, 3.0, 1.0], capacity_parts=2)

    result = run_line(config, RunConfig(run_length_h=300.0))

    # The completions fall at 5 + 3k hours, and the last one before 300 is
    # k = 98, so 99 parts reach the sink.
    assert result.completion_times_h[:3] == (5.0, 8.0, 11.0)
    assert result.parts_produced == 99


def test_no_part_is_lost_or_created_inside_the_line():
    config = make_line([1.0, 2.0, 1.0, 3.0], capacity_parts=3)
    env, line = build(config)

    env.run(until=500.0)

    in_machines = len(config.machines)
    in_buffers = sum(buffer.level_parts for buffer in line.buffers)
    assert line.source.parts_released == line.sink.parts_produced + in_buffers + in_machines


def test_two_runs_with_the_same_seed_are_identical():
    first = run_line(LineConfig(), RunConfig(run_length_h=500.0, seed=7))
    second = run_line(LineConfig(), RunConfig(run_length_h=500.0, seed=7))

    assert first == second


def test_streams_of_different_machines_differ_and_repeat_for_the_same_seed():
    first = spawn_machine_streams(3, 2)
    again = spawn_machine_streams(3, 2)

    draws = [stream.degradation.random() for stream in first]
    assert draws[0] != draws[1]
    assert draws == [stream.degradation.random() for stream in again]
    assert isinstance(first[0].degradation, np.random.Generator)
