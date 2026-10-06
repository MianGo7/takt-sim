import dataclasses
import json

import pandas as pd
import pytest

from takt.analysis import replication_table, summary_table
from takt.cli import _all, main
from takt.config import BufferConfig, LineConfig, reference_line_with_degradation
from takt.experiment import (
    ExperimentConfig,
    Scenario,
    replication_seeds,
    run_experiment,
    s0_experiment,
    s1_experiment,
)


def two_buffer_scenarios() -> tuple[Scenario, Scenario]:
    base = reference_line_with_degradation()
    small = dataclasses.replace(base, buffers=tuple(BufferConfig(5) for _ in base.buffers))
    return Scenario("large", base), Scenario("small", small)


def short_experiment(replications: int = 3) -> ExperimentConfig:
    return ExperimentConfig(
        name="short",
        scenarios=two_buffer_scenarios(),
        seed=5,
        replications=replications,
        warmup_h=50.0,
        run_length_h=500.0,
    )


def test_replication_seeds_are_reproducible_and_distinct():
    first = replication_seeds(7, 5)

    assert first == replication_seeds(7, 5)
    assert len(set(first)) == 5
    assert first != replication_seeds(8, 5)


def test_an_experiment_is_repeated_exactly_from_its_definition():
    assert run_experiment(short_experiment()) == run_experiment(short_experiment())


def test_scenarios_use_the_same_seed_in_the_same_replication():
    results = run_experiment(short_experiment())

    seeds = {s: [r.seed for r in results if r.scenario == s] for s in ("large", "small")}
    assert seeds["large"] == seeds["small"]


def test_scenarios_that_differ_only_in_the_buffers_see_identical_degradation():
    results = run_experiment(short_experiment())

    by_scenario = {s: [r for r in results if r.scenario == s] for s in ("large", "small")}
    # The degradation does not depend on the flow of parts (A2), so with
    # common random numbers the machine availability is the same, while the
    # output differs because of the buffers.
    for large, small in zip(by_scenario["large"], by_scenario["small"], strict=True):
        assert [m.availability for m in large.indicators.machines] == [
            m.availability for m in small.indicators.machines
        ]
        assert large.indicators.mean_wip_parts != small.indicators.mean_wip_parts


def test_replications_of_one_scenario_differ():
    results = run_experiment(short_experiment())

    availabilities = {
        r.indicators.machines[2].availability for r in results if r.scenario == "large"
    }
    assert len(availabilities) > 1


def test_the_observation_window_starts_after_the_warm_up():
    config = ExperimentConfig(
        name="deterministic",
        scenarios=(Scenario("S0", LineConfig()),),
        replications=1,
        warmup_h=100.0,
        run_length_h=200.0,
    )

    result = run_experiment(config)[0]

    assert result.indicators.parts_produced == 200
    assert result.indicators.throughput_per_h == 1.0


def test_summary_has_one_interval_per_scenario_and_indicator():
    results = run_experiment(short_experiment())

    summary = summary_table(results)
    row = summary[(summary.scenario == "large") & (summary.indicator == "throughput_per_h")].iloc[0]

    assert row.n == 3
    assert row.lower < row["mean"] < row.upper
    assert row.confidence_level == 0.95
    assert len(replication_table(results)) == 6


def test_the_experiment_of_the_reference_case_has_its_run_length_and_replications():
    config = s1_experiment()

    assert config.replications == 50
    assert config.run_length_h == 10_080.0
    assert config.warmup_h == 252.0


def test_the_deterministic_experiment_has_no_warm_up_and_one_replication():
    config = s0_experiment()

    assert (config.replications, config.warmup_h) == (1, 0.0)


@pytest.mark.parametrize(
    "field, value", [("replications", 0), ("warmup_h", -1.0), ("run_length_h", 0.0)]
)
def test_experiment_rejects_invalid_settings(field, value):
    with pytest.raises(ValueError, match=field):
        dataclasses.replace(short_experiment(), **{field: value})


def test_command_runs_an_experiment_and_writes_its_tables_and_definition(tmp_path, capsys):
    main(["--out", str(tmp_path), "run", "s0"])

    folder = tmp_path / "s0"
    assert {p.name for p in folder.iterdir()} == {
        "replications.csv",
        "summary.csv",
        "definition.json",
    }
    assert json.loads((folder / "definition.json").read_text())["seed"] == 2026
    assert "parts_produced" in capsys.readouterr().out


def test_a_scenario_with_a_threshold_cannot_be_run_without_it(tmp_path):
    with pytest.raises(SystemExit, match="--threshold"):
        main(["--out", str(tmp_path), "--workers", "1", "run", "s3"])


def test_the_command_for_the_report_writes_every_table_and_figure(tmp_path, capsys):
    def short(config: ExperimentConfig) -> ExperimentConfig:
        return dataclasses.replace(config, replications=2, warmup_h=20.0, run_length_h=200.0)

    _all(tmp_path / "figures", tmp_path / "results", workers=1, adjust=short)

    written = {p.name for p in (tmp_path / "figures").iterdir()}
    assert written == {
        "validation-s1.csv",
        "validation-s1-summary.csv",
        "s0-summary.csv",
        "s1-summary.csv",
        "s2-summary.csv",
        "s2-vs-s1.csv",
        "s2-vs-published.csv",
        "s2-threshold.pdf",
        "s2-threshold.png",
        "s3-summary.csv",
        "s3-vs-s1.csv",
        "s3-signal.pdf",
        "s3-signal.png",
        "s4-summary.csv",
        "s4-condition-based-vs-run-to-failure.csv",
        "s4-buffer.pdf",
        "s4-buffer.png",
        "warmup-check.csv",
    }
    published = pd.read_csv(tmp_path / "figures" / "s2-vs-published.csv")
    assert published.groupby("scenario")["highest_quality"].first().sum() == 1
    transient = pd.read_csv(tmp_path / "figures" / "warmup-check.csv")
    assert set(transient["experiment"]) == {"s1", "s2", "s3", "s4"}
    assert "setting of S3 and S4" in capsys.readouterr().out
    assert (tmp_path / "results" / "s4" / "definition.json").exists()
