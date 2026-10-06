import dataclasses
import math
import statistics

import pytest
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
from takt.experiment import ExperimentConfig, Scenario, line_indicators, run_experiment
from takt.model import Line, run_line, spawn_machine_streams

FAILURE_STEPS = 8
CORRECTIVE_REPAIR_H = 20.0


def analytic_cycle_h(degradation: DegradationConfig) -> tuple[float, float]:
    """Mean time to failure and mean cycle from failure to failure in hours."""
    interval_h = degradation.weibull_scale_h * math.gamma(1 + 1 / degradation.weibull_shape)
    mttf_h = FAILURE_STEPS * interval_h
    return mttf_h, mttf_h + CORRECTIVE_REPAIR_H


def single_machine_replications(degradation: DegradationConfig) -> list:
    # A2: the degradation does not depend on the flow of parts, so one offer
    # per 1,000 hours keeps the runs cheap without changing what is measured.
    line = LineConfig(
        machines=(MachineConfig(degradation=degradation),),
        buffers=(),
        arrival_interval_h=1_000.0,
    )
    config = ExperimentConfig(
        name="analytic",
        scenarios=(Scenario("single", line),),
        seed=12,
        replications=100,
        warmup_h=1_000.0,
        run_length_h=10_080.0,
    )
    return [r.indicators.machines[0] for r in run_experiment(config)]


def standard_errors_from(values: list[float], expected: float) -> float:
    return abs(statistics.fmean(values) - expected) / (
        statistics.stdev(values) / math.sqrt(len(values))
    )


# A deviation of four standard errors has a probability of about 6e-5 for a
# correct model, so the fixed seed does not decide the outcome by luck.
TOLERANCE_STANDARD_ERRORS = 4.0


@pytest.mark.parametrize(
    "degradation",
    [DegradationConfig(1.5, 12.0), DegradationConfig(0.9, 3.0)],
    ids=["regular machine", "machine M3"],
)
def test_availability_and_repair_count_match_the_analytic_values(degradation):
    mttf_h, cycle_h = analytic_cycle_h(degradation)

    machines = single_machine_replications(degradation)

    availability = [m.availability for m in machines]
    repairs = [float(m.repairs) for m in machines]
    assert standard_errors_from(availability, mttf_h / cycle_h) < TOLERANCE_STANDARD_ERRORS
    assert standard_errors_from(repairs, 10_080.0 / cycle_h) < TOLERANCE_STANDARD_ERRORS


def test_analytic_values_of_the_reference_machines_are_those_of_the_concept():
    regular = analytic_cycle_h(DegradationConfig(1.5, 12.0))
    m3 = analytic_cycle_h(DegradationConfig(0.9, 3.0))

    assert regular[0] == pytest.approx(86.66, abs=0.01)
    assert m3[0] == pytest.approx(25.25, abs=0.01)
    assert regular[0] / regular[1] == pytest.approx(0.812, abs=0.001)
    assert m3[0] / m3[1] == pytest.approx(0.558, abs=0.001)


def build(config: LineConfig, seed: int = 0) -> tuple[simpy.Environment, Line]:
    env = simpy.Environment()
    return env, Line(env, config, spawn_machine_streams(seed, len(config.machines)))


def parts_in_line(line: Line) -> int:
    return sum(b.level_parts for b in line.buffers) + sum(m.holding_part for m in line.machines)


@pytest.mark.parametrize("capacity_parts", [0, 1, 10])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_every_released_part_is_produced_scrapped_or_still_in_the_line(seed, capacity_parts):
    base = reference_line_with_degradation()
    config = dataclasses.replace(
        base, buffers=tuple(BufferConfig(capacity_parts) for _ in base.buffers)
    )
    env, line = build(config, seed)

    for until_h in (50.0, 333.3, 1_000.0, 2_500.0):
        env.run(until=until_h)

        scrapped = sum(m.parts_scrapped for m in line.machines)
        released = line.source.parts_released
        assert released == line.sink.parts_produced + scrapped + parts_in_line(line)


def test_a_buffer_of_capacity_zero_blocks_the_giving_machine_until_the_next_one_asks():
    config = LineConfig(
        machines=(MachineConfig(cycle_time_h=1.0), MachineConfig(cycle_time_h=2.0)),
        buffers=(BufferConfig(capacity_parts=0),),
    )

    result = run_line(config, RunConfig(run_length_h=100.0))
    indicators = line_indicators(result, 11.0, 99.0)

    # The first machine finishes a part every two hours, waits one hour for
    # the second machine, and nothing ever waits between them.
    assert result.completion_times_h[:4] == (3.0, 5.0, 7.0, 9.0)
    assert indicators.machines[0].share_blocked == 0.5
    assert indicators.mean_wip_parts == 0.0


def test_a_line_of_equal_machines_loses_nothing_with_buffers_of_capacity_zero():
    config = LineConfig(buffers=tuple(BufferConfig(0) for _ in range(5)))

    result = run_line(config, RunConfig(run_length_h=10_080.0))

    assert result.parts_produced == 10_074


def test_a_machine_that_fails_while_waiting_at_a_link_of_capacity_zero_takes_no_part():
    nearly_constant = DegradationConfig(weibull_shape=1000.0, weibull_scale_h=1.0)
    config = LineConfig(
        machines=(MachineConfig(), MachineConfig(degradation=nearly_constant)),
        buffers=(BufferConfig(capacity_parts=0),),
        arrival_interval_h=5.0,
    )
    env, line = build(config)

    env.run(until=33.0)

    repair = line.maintainers.records[0]
    # The second machine fails at about 8 hours while it waits for a part,
    # and the part that the first machine finished at 11 hours reaches it only
    # after the repair. The next failure follows at about 36 hours.
    assert line.machines[1].parts_scrapped == 0
    assert 7.9 < repair.created_at_h < 8.1
    assert line.sink.completion_times_h[2] == repair.finished_at_h + 1.0


def test_a_very_large_buffer_never_blocks_the_machine_before_it():
    config = LineConfig(
        machines=(MachineConfig(cycle_time_h=1.0), MachineConfig(cycle_time_h=2.0)),
        buffers=(BufferConfig(capacity_parts=1_000_000),),
    )

    result = run_line(config, RunConfig(run_length_h=100.0))
    indicators = line_indicators(result, 0.0, 100.0)

    assert indicators.machines[0].share_blocked == 0.0
    assert indicators.machines[1].share_processing == 99.0 / 100.0
    assert indicators.mean_wip_parts > 10


def test_with_one_maintainer_repairs_never_overlap_and_failed_machines_wait():
    base = reference_line_with_degradation()
    config = dataclasses.replace(base, repair=RepairConfig(maintainers=1))

    result = run_line(config, RunConfig(run_length_h=10_080.0, seed=4))
    indicators = line_indicators(result, 0.0, 10_080.0)

    repairs = sorted(result.repairs, key=lambda r: r.started_at_h)
    assert all(
        a.finished_at_h <= b.started_at_h for a, b in zip(repairs, repairs[1:], strict=False)
    )
    assert sum(m.share_awaiting_repair for m in indicators.machines) > 0.0
    assert sum(m.share_under_repair for m in indicators.machines) <= 1.0


def test_with_three_maintainers_at_most_three_repairs_run_at_the_same_time():
    result = run_line(reference_line_with_degradation(), RunConfig(run_length_h=10_080.0, seed=4))

    events = sorted(
        [(r.started_at_h, 1) for r in result.repairs]
        + [(r.finished_at_h, -1) for r in result.repairs],
        key=lambda e: (e[0], e[1]),
    )
    running = peak = 0
    for _, step in events:
        running += step
        peak = max(peak, running)
    assert peak <= 3


def test_a_machine_that_fails_while_blocked_is_blocked_again_when_its_repair_ends():
    nearly_constant = DegradationConfig(weibull_shape=1000.0, weibull_scale_h=1.0)
    config = LineConfig(
        machines=(
            MachineConfig(cycle_time_h=1.0, degradation=nearly_constant),
            MachineConfig(cycle_time_h=50.0),
        ),
        buffers=(BufferConfig(capacity_parts=1),),
    )
    env, line = build(config)

    env.run(until=30.0)

    states = [(t, s.value) for t, s in line.machines[0].state_trace if t > 7.0]
    repair_end_h = line.maintainers.records[0].finished_at_h
    # Blocked from 3 hours, under repair from about 8 hours without a wait for
    # a maintainer, and blocked again at the end of the repair, because the
    # second machine is still busy.
    assert [s for _, s in states] == ["under_repair", "blocked"]
    assert states[-1][0] == repair_end_h
