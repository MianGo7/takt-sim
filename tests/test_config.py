import dataclasses

import pytest

from takt.config import BufferConfig, LineConfig, MachineConfig, RunConfig


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
