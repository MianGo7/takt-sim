import pandas as pd
import pytest

from takt.analysis import (
    PUBLISHED_C1_PERFECT_MONITORING,
    PUBLISHED_C1_RUN_TO_FAILURE,
    MachineValues,
    break_even_repair_time_h,
    decompose_published_monitoring,
    first_event_alarm_expectation,
    run_to_failure_expectation,
    split_published_spread,
)
from takt.cli import main


def test_the_split_reproduces_the_mean_and_the_spread_that_it_started_from():
    mean, spread = 50.0, 7.0

    values = split_published_spread(mean, spread, third_is_lower=True)

    population_spread = (5 * (values.regular - mean) ** 2 + (values.third - mean) ** 2) / 6
    assert values.mean_of_machines == pytest.approx(mean)
    assert population_spread**0.5 == pytest.approx(spread)
    assert values.third < values.regular


def test_the_published_perfect_monitoring_row_splits_into_the_expected_machines():
    availability = {i.indicator: i for i in PUBLISHED_C1_PERFECT_MONITORING}["availability_mean"]
    repairs = {i.indicator: i for i in PUBLISHED_C1_PERFECT_MONITORING}["repairs_mean"]

    a = split_published_spread(availability.mean * 100, availability.spread * 100, True)
    r = split_published_spread(repairs.mean, repairs.spread, False)

    assert (a.regular, a.third) == pytest.approx((70.44, 44.34), abs=0.005)
    assert (r.regular, r.third) == pytest.approx((609.2, 968.2), abs=0.05)


def test_the_reading_agrees_with_the_analytic_values_of_the_run_to_failure_row():
    items = {i.indicator: i for i in PUBLISHED_C1_RUN_TO_FAILURE}
    availability = split_published_spread(
        items["availability_mean"].mean * 100, items["availability_mean"].spread * 100, True
    )
    repairs = split_published_spread(
        items["repairs_mean"].mean, items["repairs_mean"].spread, False
    )
    analytic_availability, analytic_repairs = run_to_failure_expectation()

    # The analytic values ignore the waiting for a maintainer, which takes
    # between 0.4 and 0.6 percent of the time in the model (journal, B5). That
    # lowers the availability of a machine by about 0.3 percentage points and
    # its repair count by about 0.4 for a regular machine and 1.2 for the third
    # machine. The observed differences are -0.31 and -0.31 percentage points
    # and -0.6 and -1.6 repairs. The tolerances of 0.5 percentage points and 2
    # repairs cover them, the rounding of the published values, and the
    # sampling error of a mean of 50 replications, which is about 0.05
    # percentage points and 0.3 and 0.5 repairs, and not more.
    assert availability.regular == pytest.approx(analytic_availability.regular * 100, abs=0.5)
    assert availability.third == pytest.approx(analytic_availability.third * 100, abs=0.5)
    assert repairs.regular == pytest.approx(analytic_repairs.regular, abs=2.0)
    assert repairs.third == pytest.approx(analytic_repairs.third, abs=2.0)
    assert availability.regular < analytic_availability.regular * 100
    assert repairs.third < analytic_repairs.third


def test_the_analytic_values_of_the_run_to_failure_are_those_of_the_concept():
    availability, repairs = run_to_failure_expectation()

    assert (availability.regular, availability.third) == pytest.approx((0.8125, 0.5580), abs=1e-4)
    assert (repairs.regular, repairs.third) == pytest.approx((94.50, 222.75), abs=0.01)
    assert availability.mean_of_machines == pytest.approx(0.770, abs=0.001)


@pytest.mark.parametrize(
    ("repair_time_h", "mean_availability", "mean_repairs"),
    [(2.5, 78.2, 880.2), (5.0, 64.9, 708.4)],
)
def test_the_alarm_at_the_first_degradation_event_has_the_expected_mean_of_six(
    repair_time_h, mean_availability, mean_repairs
):
    availability, repairs = first_event_alarm_expectation(0.5, repair_time_h)

    assert availability.mean_of_machines * 100 == pytest.approx(mean_availability, abs=0.05)
    # The repair count of 2.5 hours is 880.13 and the expected value is
    # given as 880.2, so the tolerance is 0.1.
    assert repairs.mean_of_machines == pytest.approx(mean_repairs, abs=0.1)


def test_the_alarm_at_the_first_degradation_event_has_the_expected_values_per_machine():
    short = first_event_alarm_expectation(0.5, 2.5)
    long = first_event_alarm_expectation(0.5, 5.0)

    assert short[0].regular == pytest.approx(0.8193, abs=1e-4)
    assert short[1].regular == pytest.approx(728.7, abs=0.05)
    assert short[0].third == pytest.approx(0.5939, abs=1e-4)
    assert long[1].third == pytest.approx(1164.4, abs=0.05)


def test_the_break_even_repair_time_is_about_two_and_a_half_hours():
    machines, mean_of_six = break_even_repair_time_h(0.5)

    assert machines.regular == pytest.approx(2.6, abs=0.05)
    assert machines.third == pytest.approx(2.9, abs=0.05)
    # At the break-even the alarm gives the availability of the run to failure.
    availability, _ = first_event_alarm_expectation(0.5, mean_of_six)
    rtf, _ = run_to_failure_expectation()
    assert availability.mean_of_machines == pytest.approx(rtf.mean_of_machines)
    assert machines.regular < mean_of_six < machines.third


def test_the_table_has_the_implied_downtime_per_repair_of_the_published_row():
    table = decompose_published_monitoring()

    def value(section, case_part, machine, quantity):
        rows = table[
            (table["section"] == section)
            & table["case"].str.contains(case_part)
            & (table["machine"] == machine)
            & (table["quantity"] == quantity)
        ]
        assert len(rows) == 1
        return float(rows["value"].iloc[0])

    perfect = "perfect monitoring"
    assert value("decomposition", perfect, "regular machine", "downtime per repair") == (
        pytest.approx(4.89, abs=0.005)
    )
    assert value("decomposition", perfect, "third machine", "downtime per repair") == (
        pytest.approx(5.80, abs=0.005)
    )
    # The same reading applied to the run to failure gives about the documented
    # 20 hours, plus the waiting for a maintainer.
    rtf = "run-to-failure"
    assert value("decomposition", rtf, "regular machine", "downtime per repair") == (
        pytest.approx(20.0, abs=0.5)
    )
    assert value("decomposition", rtf, "third machine", "downtime per repair") == (
        pytest.approx(20.0, abs=0.5)
    )
    assert set(table.columns) == {
        "section",
        "case",
        "machine",
        "quantity",
        "value",
        "unit",
        "basis",
    }


def test_the_command_writes_the_table_that_the_function_returns(tmp_path):
    main(["--out", str(tmp_path), "decompose", "--figures", str(tmp_path)])

    written = pd.read_csv(tmp_path / "published-monitoring-decomposition.csv")
    expected = decompose_published_monitoring()
    pd.testing.assert_frame_equal(written, expected, check_exact=False, rtol=1e-12)


def test_machine_values_average_over_six_machines_of_which_five_are_identical():
    assert MachineValues(10.0, 40.0).mean_of_machines == pytest.approx(15.0)
