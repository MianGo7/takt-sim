import math

import numpy as np
import pytest

from takt.analysis import estimate, moving_average, mser_truncation, welch


def test_confidence_interval_of_five_values_uses_the_t_distribution():
    result = estimate([1.0, 2.0, 3.0, 4.0, 5.0])

    # t(0.975, 4) = 2.7764 and the standard error is sqrt(2.5 / 5).
    assert result.mean == 3.0
    assert result.half_width == pytest.approx(2.7764451 * math.sqrt(0.5), rel=1e-6)
    assert (result.lower, result.upper) == (
        result.mean - result.half_width,
        result.mean + result.half_width,
    )
    assert result.n == 5


def test_a_single_replication_has_a_mean_but_no_interval():
    result = estimate([4.0])

    assert result.mean == 4.0
    assert math.isnan(result.half_width)


def test_replications_without_a_value_are_left_out_of_the_mean():
    result = estimate([1.0, math.nan, 3.0])

    assert result.mean == 2.0
    assert result.n == 2


def test_interval_covers_the_true_mean_in_about_95_percent_of_samples():
    rng = np.random.default_rng(1)
    trials, covered = 2_000, 0
    for _ in range(trials):
        e = estimate(rng.normal(10.0, 3.0, size=20).tolist())
        covered += e.lower <= 10.0 <= e.upper

    # The coverage of 2,000 trials has a standard error of 0.5 percentage
    # points, and the tolerance is three of them.
    assert covered / trials == pytest.approx(0.95, abs=0.015)


def test_moving_average_shrinks_its_window_at_the_start_and_drops_the_incomplete_end():
    smoothed = moving_average([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], window=2)

    assert smoothed == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_welch_averages_the_replications_before_smoothing():
    result = welch([[0.0, 2.0, 4.0, 6.0], [2.0, 4.0, 6.0, 8.0]], window=1)

    assert result.averaged == (1.0, 3.0, 5.0, 7.0)
    assert result.smoothed == (1.0, 3.0, 5.0)


def test_mser_truncates_exactly_at_the_end_of_an_obvious_transient():
    series = [50.0, 40.0, 30.0, 20.0, 10.0] + [5.1, 4.9] * 20

    assert mser_truncation(series) == 5


def test_mser_keeps_a_series_without_a_transient():
    series = [5.1, 4.9] * 20

    assert mser_truncation(series) == 0
