import math

import pytest

from takt.analysis import (
    PUBLISHED_C1_RUN_TO_FAILURE,
    PublishedValue,
    compare_with_published,
    replication_table,
)
from takt.config import reference_line_with_degradation
from takt.experiment import ExperimentConfig, Scenario, run_experiment


@pytest.fixture(scope="module")
def results():
    config = ExperimentConfig(
        name="short",
        scenarios=(Scenario("S1", reference_line_with_degradation()),),
        seed=3,
        replications=6,
        warmup_h=50.0,
        run_length_h=1_000.0,
    )
    return run_experiment(config)


def test_published_values_are_those_of_table_one_for_the_reference_case():
    by_name = {p.indicator: p for p in PUBLISHED_C1_RUN_TO_FAILURE}

    assert by_name["availability_mean"].mean == 0.7670
    assert by_name["repairs_mean"].mean == 115.12
    assert by_name["parts_produced"].mean == 4730.16
    assert by_name["mean_quality"].mean == 0.60
    assert by_name["parts_produced"].spread == 53.638


def test_a_published_mean_equal_to_the_model_mean_agrees_with_a_difference_of_zero(results):
    mean = replication_table(results)["parts_produced"].mean()
    published = (PublishedValue("parts_produced", mean, 50.0, "replications", 0.005),)

    row = compare_with_published(results, published).iloc[0]

    assert row["difference"] == pytest.approx(0.0, abs=1e-9)
    assert row["agrees_within_ci_and_rounding"]
    assert row["z_over_both_standard_errors"] == pytest.approx(0.0, abs=1e-9)


def test_a_published_mean_far_from_the_model_mean_does_not_agree(results):
    mean = replication_table(results)["parts_produced"].mean()
    published = (PublishedValue("parts_produced", mean + 1_000.0, 50.0, "replications", 0.005),)

    row = compare_with_published(results, published).iloc[0]

    assert not row["agrees_within_ci_and_rounding"]
    assert row["z_over_both_standard_errors"] < -10


def test_the_standard_error_of_the_published_mean_is_marked_as_a_stand_in_for_other_spreads(
    results,
):
    rows = compare_with_published(results).set_index("indicator")
    row = rows.loc["availability_mean"]

    assert not row["published_se_known"]
    assert rows.loc["parts_produced"]["published_se_known"]
    assert math.isfinite(row["z_over_both_standard_errors"])
    assert row["spread_over"] == "machines"
    assert 0.0 < row["spread"] < 0.5
