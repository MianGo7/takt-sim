import dataclasses
import math

import pytest
import simpy

from takt.config import (
    BufferConfig,
    ConditionBasedConfig,
    DegradationConfig,
    LineConfig,
    MachineConfig,
    RepairConfig,
    RunConfig,
    reference_line_condition_based,
    reference_line_with_degradation,
)
from takt.experiment import line_indicators
from takt.model import (
    ConditionBased,
    Line,
    MachineState,
    RepairKind,
    RunToFailure,
    run_line,
    spawn_machine_streams,
)

# A shape of 1000 makes the Weibull draw almost constant, within about half a
# percent of the scale, so that the health of a machine at a given time is
# known while the draws still come from its random number stream.
NEARLY_CONSTANT_SHAPE = 1000.0


def nearly_constant(scale_h: float) -> DegradationConfig:
    return DegradationConfig(weibull_shape=NEARLY_CONSTANT_SHAPE, weibull_scale_h=scale_h)


def build(config: LineConfig, seed: int = 0) -> tuple[simpy.Environment, Line]:
    env = simpy.Environment()
    return env, Line(env, config, spawn_machine_streams(seed, len(config.machines)))


def two_machines(
    first: DegradationConfig | None,
    second: DegradationConfig | None,
    policy: ConditionBasedConfig,
    cycle_times_h: tuple[float, float] = (1.0, 1.0),
    capacity_parts: int = 100,
    repair: RepairConfig | None = None,
) -> LineConfig:
    return LineConfig(
        machines=(
            MachineConfig(cycle_time_h=cycle_times_h[0], degradation=first),
            MachineConfig(cycle_time_h=cycle_times_h[1], degradation=second),
        ),
        buffers=(BufferConfig(capacity_parts),),
        repair=repair or RepairConfig(maintainers=1),
        policy=policy,
    )


def test_repair_time_follows_the_three_health_classes_of_the_reference_case():
    repair = RepairConfig()

    assert repair.repair_time_h(0.0) == 20.0
    assert [repair.repair_time_h(h) for h in (0.125, 0.25, 0.375)] == [5.0, 5.0, 5.0]
    # A6: a health of exactly 0.5 belongs to the shorter class.
    assert [repair.repair_time_h(h) for h in (0.5, 0.625, 0.875, 1.0)] == [2.5] * 4


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_an_ideal_signal_with_a_threshold_below_every_health_value_reproduces_run_to_failure(seed):
    run = RunConfig(run_length_h=2_000.0, seed=seed)

    baseline = run_line(reference_line_with_degradation(), run)
    monitored = run_line(reference_line_condition_based(alarm_threshold=0.0), run)

    assert monitored == baseline
    assert monitored.alarms == ()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_a_signal_that_never_raises_an_alarm_reproduces_run_to_failure(seed):
    run = RunConfig(run_length_h=2_000.0, seed=seed)

    baseline = run_line(reference_line_with_degradation(), run)
    silent = reference_line_condition_based(
        alarm_threshold=0.5, detection_probability=0.0, false_alarm_probability=0.0
    )

    assert run_line(silent, run) == baseline


def test_the_policy_is_exchanged_by_the_configuration_alone():
    _, run_to_failure = build(reference_line_with_degradation())
    _, monitored = build(reference_line_condition_based(0.5))

    assert isinstance(run_to_failure.policy, RunToFailure)
    assert isinstance(monitored.policy, ConditionBased)


def test_a_machine_with_a_pending_work_order_keeps_producing_until_the_maintainer_arrives():
    # M2 is repaired from 3 hours on for 30 hours, so the only maintainer is
    # busy. M1 reaches a health of 0.5 at 21.2 hours, and the reading at 22
    # hours raises its alarm. Its order waits until the maintainer is free.
    repair = RepairConfig(maintainers=1, deteriorated_repair_time_h=30.0)
    config = two_machines(
        nearly_constant(5.3),
        nearly_constant(0.55),
        ConditionBasedConfig(alarm_threshold=0.5),
        repair=repair,
    )
    env, line = build(config)

    env.run(until=32.0)

    occupant_states = line.machines[1].state_trace
    assert (3.0, MachineState.UNDER_REPAIR) in occupant_states
    states = {t: s for t, s in line.machines[0].state_trace}
    assert line.machines[0].work_order_open
    assert line.policy.alarms[1].machine == "M1" and line.policy.alarms[1].time_h == 22.0
    assert line.machines[0].state_trace[-1][1] is MachineState.PROCESSING
    assert MachineState.UNDER_REPAIR not in states.values()
    assert line.buffers[0].level_parts > 5


def test_the_pending_work_order_is_served_when_the_maintainer_is_free_and_not_created_again():
    repair = RepairConfig(maintainers=1, deteriorated_repair_time_h=30.0)
    config = two_machines(
        nearly_constant(5.3),
        nearly_constant(0.55),
        ConditionBasedConfig(alarm_threshold=0.5),
        repair=repair,
    )
    env, line = build(config)

    env.run(until=70.0)

    own = [r for r in line.maintainers.records if r.machine == "M1"][0]
    first = [r for r in line.maintainers.records if r.machine == "M2"][0]
    # The readings after 22 hours do not create another order for M1.
    assert [a.machine for a in line.policy.alarms].count("M1") == 1
    assert own.created_at_h == 22.0
    assert own.started_at_h == first.finished_at_h
    assert own.kind is RepairKind.PREVENTIVE


def test_a_machine_that_fails_while_its_work_order_waits_receives_the_corrective_repair():
    # M1 reaches 0.5 at 8.8 hours and is read at 9 hours, but fails at 17.6
    # hours, while the maintainer is still busy with M2 until 33 hours.
    repair = RepairConfig(maintainers=1, deteriorated_repair_time_h=30.0)
    config = two_machines(
        nearly_constant(2.2),
        nearly_constant(0.55),
        ConditionBasedConfig(alarm_threshold=0.5),
        repair=repair,
    )
    env, line = build(config)

    env.run(until=60.0)

    first = [r for r in line.maintainers.records if r.machine == "M1"][0]
    occupant = [r for r in line.maintainers.records if r.machine == "M2"][0]
    assert first.kind is RepairKind.CORRECTIVE
    assert first.created_at_h == 9.0
    assert first.started_at_h == occupant.finished_at_h
    assert first.finished_at_h - first.started_at_h == pytest.approx(20.0)
    assert line.machines[0].failures[0][0] == pytest.approx(17.6, abs=0.1)


def test_a_false_alarm_causes_a_repair_of_a_healthy_machine_that_pauses_its_part():
    # Readings at 0.7, 1.4, and so on. The machine never degrades, so every
    # alarm is a false alarm. The first one meets the part that began at 0.
    policy = ConditionBasedConfig(
        alarm_threshold=0.0, sensing_interval_h=0.7, false_alarm_probability=1.0
    )
    config = LineConfig(
        machines=(MachineConfig(),), buffers=(), repair=RepairConfig(), policy=policy
    )

    result = run_line(config, RunConfig(run_length_h=10.0))

    alarm = result.alarms[0]
    repair = result.repairs[0]
    assert (alarm.time_h, alarm.health, alarm.true_alarm) == (0.7, 1.0, False)
    assert repair.kind is RepairKind.PREVENTIVE
    assert repair.finished_at_h - repair.started_at_h == pytest.approx(2.5)
    # A11: the part keeps the 0.7 hours of work done and finishes 0.3 hours
    # after the repair, and nothing is scrapped.
    assert result.completion_times_h[0] == pytest.approx(0.7 + 2.5 + 0.3)
    assert result.parts_scrapped == 0
    assert line_indicators(result, 0.0, 10.0).alarms_false == len(result.alarms)


def test_a_preventive_repair_starts_with_the_duration_of_the_health_class():
    degradation = nearly_constant(1.3)

    def first_repair(threshold: float):
        policy = ConditionBasedConfig(alarm_threshold=threshold)
        config = LineConfig(
            machines=(MachineConfig(degradation=degradation),),
            buffers=(),
            arrival_interval_h=1_000.0,
            policy=policy,
        )
        result = run_line(config, RunConfig(run_length_h=40.0))
        return result.alarms[0], result.repairs[0]

    mild_alarm, mild = first_repair(0.5)
    deteriorated_alarm, deteriorated = first_repair(0.375)

    # Four events by 5.2 hours give a health of 0.5, five by 6.5 hours 0.375.
    assert (mild_alarm.time_h, mild_alarm.health) == (6.0, 0.5)
    assert mild.finished_at_h - mild.started_at_h == pytest.approx(2.5)
    assert (deteriorated_alarm.time_h, deteriorated_alarm.health) == (7.0, 0.375)
    assert deteriorated.finished_at_h - deteriorated.started_at_h == pytest.approx(5.0)


def test_a_blocked_machine_is_repaired_without_losing_its_part_and_is_blocked_again_after():
    config = two_machines(
        nearly_constant(1.3),
        None,
        ConditionBasedConfig(alarm_threshold=0.5),
        cycle_times_h=(1.0, 50.0),
        capacity_parts=1,
    )
    env, line = build(config)

    env.run(until=12.0)

    states = [(t, s.value) for t, s in line.machines[0].state_trace if t >= 3.0]
    assert [s for _, s in states] == ["blocked", "under_repair", "blocked"]
    assert states[1][0] == 6.0
    assert states[2][0] == pytest.approx(8.5)
    assert line.machines[0].parts_scrapped == 0


@pytest.mark.parametrize(
    ("detection", "false_alarm", "threshold"),
    [(0.7, 0.0, 1.0), (1.0, 0.3, 0.0)],
    ids=["detection probability", "false alarm probability"],
)
def test_the_error_rates_are_the_share_of_readings_that_raise_an_alarm(
    detection, false_alarm, threshold
):
    # The repair is much shorter than the reading interval, so every reading
    # meets a machine without an open work order. The machine never degrades,
    # so its health of 1 is at or below a threshold of 1 and above one of 0.
    policy = ConditionBasedConfig(
        alarm_threshold=threshold,
        detection_probability=detection,
        false_alarm_probability=false_alarm,
    )
    config = LineConfig(
        machines=(MachineConfig(),),
        buffers=(),
        arrival_interval_h=1_000.0,
        repair=RepairConfig(mild_repair_time_h=0.01),
        policy=policy,
    )
    readings = 20_000

    result = run_line(config, RunConfig(run_length_h=readings + 0.5))

    probability = detection if threshold == 1.0 else false_alarm
    # Four standard deviations of a binomial count, which a correct sampler
    # exceeds with a probability of about 6e-5.
    tolerance = 4 * math.sqrt((readings - 1) * probability * (1 - probability))
    assert len(result.alarms) == pytest.approx((readings - 1) * probability, abs=tolerance)


@pytest.mark.parametrize("seed", [1, 2])
def test_every_released_part_is_accounted_for_with_preventive_repairs_and_false_alarms(seed):
    config = reference_line_condition_based(
        alarm_threshold=0.5, detection_probability=0.8, false_alarm_probability=0.02
    )
    env, line = build(config, seed)

    for until_h in (50.0, 333.3, 1_000.0):
        env.run(until=until_h)

        scrapped = sum(m.parts_scrapped for m in line.machines)
        in_line = sum(b.level_parts for b in line.buffers) + sum(
            m.holding_part for m in line.machines
        )
        assert line.source.parts_released == line.sink.parts_produced + scrapped + in_line


def test_ideal_alarms_come_from_readings_at_or_below_the_threshold_and_add_preventive_repairs():
    run = RunConfig(run_length_h=3_000.0, seed=5)

    baseline = line_indicators(run_line(reference_line_with_degradation(), run), 0.0, 3_000.0)
    monitored_result = run_line(reference_line_condition_based(0.5), run)
    monitored = line_indicators(monitored_result, 0.0, 3_000.0)

    assert monitored.alarms_true > 0
    assert monitored.alarms_false == 0
    assert all(a.health <= 0.5 for a in monitored_result.alarms)
    assert sum(m.repairs_preventive for m in monitored.machines) > 0
    assert sum(m.repairs for m in monitored.machines) > sum(m.repairs for m in baseline.machines)


def test_condition_based_configuration_rejects_values_outside_their_range():
    with pytest.raises(ValueError, match="alarm_threshold"):
        ConditionBasedConfig(alarm_threshold=1.5)
    with pytest.raises(ValueError, match="detection_probability"):
        ConditionBasedConfig(alarm_threshold=0.5, detection_probability=-0.1)
    with pytest.raises(ValueError, match="false_alarm_probability"):
        ConditionBasedConfig(alarm_threshold=0.5, false_alarm_probability=1.1)
    with pytest.raises(ValueError, match="sensing_interval_h"):
        ConditionBasedConfig(alarm_threshold=0.5, sensing_interval_h=0.0)


def test_scenarios_that_differ_in_the_policy_alone_have_the_same_line():
    base = reference_line_with_degradation()
    monitored = reference_line_condition_based(0.5)

    assert dataclasses.replace(monitored, policy=base.policy) == base
