import dataclasses
import math

import pytest

from takt.analysis import (
    best_scenario,
    difference_table,
    paired_difference,
    paired_table,
    summary_table,
)
from takt.config import (
    BufferConfig,
    ConditionBasedConfig,
    LineConfig,
    RunConfig,
    reference_line_condition_based,
    reference_line_with_degradation,
)
from takt.experiment import (
    EXPERIMENTS,
    S2_THRESHOLDS,
    ExperimentConfig,
    Scenario,
    _segments,
    binned_series,
    run_experiment,
    s2_experiment,
    s3_experiment,
    s4_experiment,
)
from takt.model import run_line


def shortened(config: ExperimentConfig, replications: int = 2) -> ExperimentConfig:
    return dataclasses.replace(config, replications=replications, warmup_h=20.0, run_length_h=300.0)


def test_s2_varies_the_alarm_threshold_over_every_health_value_with_an_ideal_signal():
    config = s2_experiment()

    thresholds = [dict(s.settings)["alarm_threshold"] for s in config.scenarios]
    assert thresholds == [0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875]
    assert thresholds == list(S2_THRESHOLDS)
    for scenario in config.scenarios:
        policy = scenario.line.policy
        assert isinstance(policy, ConditionBasedConfig)
        assert (policy.detection_probability, policy.false_alarm_probability) == (1.0, 0.0)


def test_s3_is_a_grid_of_detection_and_false_alarm_probabilities_at_one_threshold():
    config = s3_experiment(0.5)

    settings = [dict(s.settings) for s in config.scenarios]
    assert len(settings) == 16
    assert {s["alarm_threshold"] for s in settings} == {0.5}
    assert {s["detection_probability"] for s in settings} == {1.0, 0.9, 0.75, 0.5}
    assert {s["false_alarm_probability"] for s in settings} == {0.0, 0.002, 0.01, 0.05}
    # The corner with an ideal signal is the scenario of S2 at that threshold.
    ideal = next(s for s in config.scenarios if dict(s.settings)["detection_probability"] == 1.0)
    assert ideal.line == reference_line_condition_based(0.5)


def test_s4_changes_only_the_buffer_capacity_and_the_policy():
    config = s4_experiment(0.5)

    by_name = {s.name: s for s in config.scenarios}
    assert len(by_name) == 14
    reference = by_name["S4 run-to-failure capacity 10"].line
    assert reference == reference_line_with_degradation()
    assert by_name["S4 condition-based capacity 10"].line == reference_line_condition_based(0.5)
    small = by_name["S4 condition-based capacity 0"].line
    assert [b.capacity_parts for b in small.buffers] == [0] * 5
    assert dataclasses.replace(
        small, buffers=tuple(BufferConfig(10) for _ in small.buffers)
    ) == reference_line_condition_based(0.5)


def test_all_experiments_use_the_same_root_seed_so_that_their_replications_pair():
    seeds = {EXPERIMENTS["s1"]().seed, EXPERIMENTS["s2"]().seed, s3_experiment(0.5).seed}

    assert len(seeds) == 1


def test_binned_series_gives_exact_values_for_the_deterministic_line():
    result = run_line(LineConfig(), RunConfig(run_length_h=120.0))

    output, wip = binned_series(result, 12.0)

    # The first part leaves after six hours, so the first bin has six parts.
    assert output == [6.0] + [12.0] * 9
    assert wip == [0.0] * 10


def test_binned_series_agrees_with_a_direct_integral_of_the_buffer_levels():
    result = run_line(reference_line_with_degradation(), RunConfig(run_length_h=600.0, seed=3))

    _, wip = binned_series(result, 12.0)

    expected = [
        math.fsum(
            level * duration_h
            for trace in result.buffer_level_traces
            for level, duration_h in _segments(trace, i * 12.0, (i + 1) * 12.0)
        )
        / 12.0
        for i in range(50)
    ]
    assert wip == pytest.approx(expected, abs=1e-9)
    assert max(wip) > 0


def test_replications_run_in_separate_processes_with_the_same_results_in_the_same_order():
    config = shortened(s2_experiment())
    config = dataclasses.replace(config, scenarios=config.scenarios[:2])

    assert run_experiment(config, workers=2) == run_experiment(config, workers=1)


def test_paired_difference_of_a_scenario_with_itself_is_zero():
    config = shortened(
        ExperimentConfig("pair", (Scenario("S1", reference_line_with_degradation()),), seed=4)
    )
    results = run_experiment(config)

    difference = paired_difference(results, results, "S1", "S1", "parts_produced")

    assert difference.mean == 0.0
    assert difference.half_width == 0.0


def test_paired_difference_is_narrower_than_the_interval_of_two_independent_runs():
    config = dataclasses.replace(
        shortened(s2_experiment(), replications=10), scenarios=s2_experiment().scenarios[3:5]
    )
    results = run_experiment(config)
    first, second = (s.name for s in config.scenarios)

    paired = paired_difference(results, results, first, second, "parts_produced")

    summary = summary_table(results).set_index(["scenario", "indicator"])
    independent = math.hypot(
        summary.loc[(first, "parts_produced"), "half_width"],
        summary.loc[(second, "parts_produced"), "half_width"],
    )
    assert paired.half_width < independent


def test_paired_difference_refuses_results_with_different_seeds():
    one = run_experiment(shortened(ExperimentConfig("a", (Scenario("S", LineConfig()),), seed=1)))
    other = run_experiment(shortened(ExperimentConfig("b", (Scenario("S", LineConfig()),), seed=2)))

    with pytest.raises(ValueError, match="different seeds"):
        paired_difference(one, other, "S", "S", "parts_produced")


def test_difference_table_marks_a_difference_as_clear_when_its_interval_excludes_zero():
    config = shortened(s2_experiment(), replications=6)
    config = dataclasses.replace(config, scenarios=(config.scenarios[0], config.scenarios[6]))
    results = run_experiment(config)
    low, high = (s.name for s in config.scenarios)

    table = paired_table(results, results, [(high, low)])

    row = table[table["indicator"] == "mean_quality"].iloc[0]
    # A threshold of 0.875 repairs at the first degradation event and keeps
    # the health higher than one of 0.125, so the quality differs clearly.
    assert row["mean_difference"] > 0
    assert bool(row["clear"])
    assert row["setting_alarm_threshold"] == 0.875
    assert len(difference_table(results, results, low)) == 14


def test_the_best_scenario_is_the_one_with_the_highest_mean_of_the_indicator():
    config = shortened(s2_experiment())
    config = dataclasses.replace(config, scenarios=config.scenarios[:3])
    summary = summary_table(run_experiment(config))
    rows = summary[summary["indicator"] == "parts_produced"]

    best = best_scenario(summary, "parts_produced")

    assert rows.set_index("scenario").loc[best, "mean"] == rows["mean"].max()


def test_s4_has_the_longer_warm_up_that_the_large_buffers_need_and_the_others_keep_the_first():
    assert s4_experiment(0.5).warmup_h == 516.0
    assert [EXPERIMENTS[n]().warmup_h for n in ("s1", "s2")] == [252.0, 252.0]
    assert s3_experiment(0.5).warmup_h == 252.0
