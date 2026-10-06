import dataclasses

import matplotlib.pyplot as plt
import pytest

from takt.analysis import summary_table
from takt.experiment import (
    ExperimentConfig,
    run_experiment,
    s1_experiment,
    s2_experiment,
    s3_experiment,
    s4_experiment,
)
from takt.plots import buffer_figure, save_figure, signal_figure, threshold_figure


def summary_of(config: ExperimentConfig):
    short = dataclasses.replace(config, replications=2, warmup_h=0.0, run_length_h=300.0)
    return summary_table(run_experiment(short))


@pytest.fixture(scope="module")
def s1_summary():
    return summary_of(s1_experiment())


def assert_written(paths, base):
    assert [p.suffix for p in paths] == [".pdf", ".png"]
    assert all(p.stat().st_size > 1_000 for p in paths)
    assert {p.stem for p in paths} == {base.name}


def test_the_threshold_figure_is_written_as_pdf_and_png(tmp_path, s1_summary):
    base = tmp_path / "threshold"

    paths = threshold_figure(summary_of(s2_experiment()), s1_summary, base)

    assert_written(paths, base)


def test_the_signal_figure_is_written_as_pdf_and_png(tmp_path):
    base = tmp_path / "signal"

    paths = signal_figure(summary_of(s3_experiment(0.5)), base)

    assert_written(paths, base)


def test_the_buffer_figure_is_written_as_pdf_and_png(tmp_path):
    base = tmp_path / "buffer"

    paths = buffer_figure(summary_of(s4_experiment(0.5)), base)

    assert_written(paths, base)


def test_the_figure_is_saved_at_300_dots_per_inch_and_closed(tmp_path):
    figure, ax = plt.subplots(figsize=(2.0, 1.0))
    ax.plot([0, 1], [0, 1])

    paths = save_figure(figure, tmp_path / "plain")

    from PIL import Image

    with Image.open(paths[1]) as image:
        assert image.info["dpi"][0] == pytest.approx(300, abs=1)
    assert not plt.fignum_exists(figure.number)
