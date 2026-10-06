import math

import pytest

from takt.config import (
    BufferConfig,
    DegradationConfig,
    LineConfig,
    MachineConfig,
    RunConfig,
)
from takt.experiment import line_indicators
from takt.model import run_line


def make_line(
    cycle_times_h: list[float],
    capacity_parts: int = 10,
    degradation: DegradationConfig | None = None,
) -> LineConfig:
    return LineConfig(
        machines=tuple(
            MachineConfig(cycle_time_h=c, degradation=degradation if i == 0 else None)
            for i, c in enumerate(cycle_times_h)
        ),
        buffers=tuple(BufferConfig(capacity_parts) for _ in cycle_times_h[1:]),
    )


def test_indicators_of_the_deterministic_line_are_exact():
    result = run_line(LineConfig(), RunConfig(run_length_h=10_080.0))

    indicators = line_indicators(result, 0.0, 10_080.0)

    assert indicators.parts_produced == 10_074
    assert indicators.throughput_per_h == 10_074 / 10_080
    assert indicators.mean_lead_time_h == 6.0
    assert indicators.mean_wip_parts == 0.0
    assert indicators.parts_scrapped == 0
    assert indicators.mean_quality == 1.0


def test_machines_of_the_deterministic_line_are_never_down_and_fill_in_one_after_another():
    result = run_line(LineConfig(), RunConfig(run_length_h=10_080.0))

    machines = line_indicators(result, 0.0, 10_080.0).machines

    assert [m.availability for m in machines] == [1.0] * 6
    assert [m.repairs for m in machines] == [0] * 6
    # Machine k+1 waits k hours for its first part and then never again.
    assert [m.share_processing for m in machines] == [(10_080 - k) / 10_080 for k in range(6)]
    assert [m.share_starved for m in machines] == [k / 10_080 for k in range(6)]
    assert [m.share_blocked for m in machines] == [0.0] * 6


def test_a_part_that_passes_six_healthy_machines_has_a_quality_of_one():
    result = run_line(LineConfig(), RunConfig(run_length_h=7.0))

    assert [part.quality for part in result.parts] == [1.0]


def test_each_machine_adds_its_share_in_proportion_to_its_health_at_the_end_of_the_cycle():
    # Degradation events fall at about 0.55, 1.1, 1.65, and so on, so a part
    # that is finished at 1, 2, 3, and 4 hours finds 1, 3, 5, and 7 steps lost.
    degradation = DegradationConfig(weibull_shape=1000.0, weibull_scale_h=0.55)
    result = run_line(make_line([1.0], degradation=degradation), RunConfig(run_length_h=4.5))

    assert [part.quality for part in result.parts] == [0.875, 0.625, 0.375, 0.125]


def test_the_quality_of_a_part_is_the_mean_health_over_all_machines():
    # The first machine has lost one step when it finishes the first part.
    degradation = DegradationConfig(weibull_shape=1000.0, weibull_scale_h=0.55)
    result = run_line(make_line([1.0, 1.0], degradation=degradation), RunConfig(run_length_h=3.0))

    assert result.parts[0].quality == (0.875 + 1.0) / 2


def test_lead_time_counts_from_entering_the_first_machine_to_the_sink():
    result = run_line(make_line([1.0, 2.0], capacity_parts=100), RunConfig(run_length_h=10.5))

    indicators = line_indicators(result, 0.0, 10.5)

    # The parts leave at 3, 5, 7, and 9 hours and entered at 0, 1, 2, and 3.
    assert result.completion_times_h == (3.0, 5.0, 7.0, 9.0)
    assert indicators.mean_lead_time_h == (3.0 + 4.0 + 5.0 + 6.0) / 4


def test_work_in_progress_is_the_time_average_of_the_parts_in_the_buffers():
    result = run_line(make_line([1.0, 2.0], capacity_parts=2), RunConfig(run_length_h=200.0))

    indicators = line_indicators(result, 100.0, 200.0)

    # The buffer is full from the filling phase until the end of the run.
    assert indicators.mean_wip_parts == 2.0


def test_the_window_excludes_what_happens_before_its_start():
    result = run_line(LineConfig(), RunConfig(run_length_h=300.0))

    indicators = line_indicators(result, 100.0, 200.0)

    assert indicators.parts_produced == 100
    assert indicators.throughput_per_h == 1.0
    assert indicators.machines[5].share_processing == 1.0


def test_time_shares_of_a_machine_add_up_to_one_and_downtime_is_the_complement_of_availability():
    degradation = DegradationConfig(weibull_shape=1000.0, weibull_scale_h=0.55)
    result = run_line(make_line([1.0], degradation=degradation), RunConfig(run_length_h=27.0))

    machine = line_indicators(result, 0.0, 27.0).machines[0]

    shares = (
        machine.share_processing
        + machine.share_starved
        + machine.share_blocked
        + machine.share_awaiting_repair
        + machine.share_under_repair
    )
    # The failure at about 4.4 hours meets a free maintainer at once, so the
    # whole downtime is repair time of 20 hours.
    assert shares == pytest.approx(1.0, abs=1e-12)
    assert machine.share_awaiting_repair == 0.0
    assert machine.share_under_repair == pytest.approx(20.0 / 27.0, abs=1e-12)
    assert machine.availability == pytest.approx(7.0 / 27.0, abs=1e-12)
    assert machine.repairs == 1


def test_a_repair_that_ends_before_the_window_is_not_counted_in_it():
    degradation = DegradationConfig(weibull_shape=1000.0, weibull_scale_h=0.55)
    result = run_line(make_line([1.0], degradation=degradation), RunConfig(run_length_h=27.0))

    machine = line_indicators(result, 26.0, 27.0).machines[0]

    assert machine.repairs == 0
    assert machine.availability == 1.0


def test_parts_scrapped_in_the_window_are_counted_by_the_time_of_the_failure():
    degradation = DegradationConfig(weibull_shape=1000.0, weibull_scale_h=0.55)
    result = run_line(make_line([1.0], degradation=degradation), RunConfig(run_length_h=27.0))

    before = line_indicators(result, 0.0, 5.0)
    after = line_indicators(result, 5.0, 27.0)

    assert (before.parts_scrapped, after.parts_scrapped) == (1, 0)


def test_a_run_without_parts_has_no_lead_time_and_no_quality():
    result = run_line(LineConfig(), RunConfig(run_length_h=3.0))

    indicators = line_indicators(result, 0.0, 3.0)

    assert math.isnan(indicators.mean_lead_time_h)
    assert math.isnan(indicators.mean_quality)
