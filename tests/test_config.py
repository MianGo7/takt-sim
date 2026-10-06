import dataclasses

import pytest

from takt.config import (
    BufferConfig,
    DegradationConfig,
    LineConfig,
    MachineConfig,
    RepairConfig,
    RunConfig,
    reference_line_with_degradation,
)


def test_default_line_is_the_reference_case():
    line = LineConfig()

    assert len(line.machines) == 6
    assert len(line.buffers) == 5
    assert all(machine.cycle_time_h == 1.0 for machine in line.machines)
    assert all(buffer.capacity_parts == 10 for buffer in line.buffers)
    assert line.arrival_interval_h == 1.0


def test_default_run_is_the_reference_case():
    run = RunConfig()

    assert run.run_length_h == 10_080.0


def test_configuration_cannot_be_changed_after_creation():
    machine = MachineConfig()

    with pytest.raises(dataclasses.FrozenInstanceError):
        machine.cycle_time_h = 2.0  # type: ignore[misc]


@pytest.mark.parametrize("cycle_time_h", [0.0, -1.0, float("inf"), float("nan")])
def test_machine_rejects_a_cycle_time_that_is_not_positive_and_finite(cycle_time_h):
    with pytest.raises(ValueError, match="cycle_time_h"):
        MachineConfig(cycle_time_h=cycle_time_h)


def test_buffer_rejects_a_capacity_below_one():
    with pytest.raises(ValueError, match="capacity_parts"):
        BufferConfig(capacity_parts=0)


def test_line_rejects_a_buffer_count_that_does_not_match_the_machines():
    with pytest.raises(ValueError, match="buffers"):
        LineConfig(machines=(MachineConfig(), MachineConfig()), buffers=())


def test_line_rejects_an_empty_list_of_machines():
    with pytest.raises(ValueError, match="at least one machine"):
        LineConfig(machines=(), buffers=())


def test_line_rejects_an_arrival_interval_that_is_not_positive():
    with pytest.raises(ValueError, match="arrival_interval_h"):
        LineConfig(arrival_interval_h=0.0)


def test_run_rejects_a_run_length_that_is_not_positive():
    with pytest.raises(ValueError, match="run_length_h"):
        RunConfig(run_length_h=0.0)


def test_run_rejects_a_negative_seed():
    with pytest.raises(ValueError, match="seed"):
        RunConfig(seed=-1)


def test_default_repair_is_the_reference_case():
    repair = RepairConfig()

    assert repair.maintainers == 3
    assert repair.corrective_repair_time_h == 20.0


def test_reference_line_with_degradation_gives_machine_three_its_own_weibull_parameters():
    line = reference_line_with_degradation()

    shapes = [(m.degradation.weibull_shape, m.degradation.weibull_scale_h) for m in line.machines]
    assert shapes == [(1.5, 12.0), (1.5, 12.0), (0.9, 3.0), (1.5, 12.0), (1.5, 12.0), (1.5, 12.0)]


@pytest.mark.parametrize("maintainers", [0, -1])
def test_repair_rejects_fewer_than_one_maintainer(maintainers):
    with pytest.raises(ValueError, match="maintainers"):
        RepairConfig(maintainers=maintainers)


def test_degradation_rejects_a_shape_that_is_not_positive():
    with pytest.raises(ValueError, match="weibull_shape"):
        DegradationConfig(weibull_shape=0.0, weibull_scale_h=1.0)
