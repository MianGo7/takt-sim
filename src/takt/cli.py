"""Command line entry point: runs experiments and writes tables and figures."""

import argparse
import dataclasses
import json
import os
import time
from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd

from takt.analysis import (
    PUBLISHED_C1_PERFECT_MONITORING,
    best_scenario,
    compare_with_published,
    decompose_published_monitoring,
    difference_table,
    mser_truncation,
    paired_table,
    replication_table,
    summary_table,
    welch,
)
from takt.experiment import (
    EXPERIMENTS,
    S4_BUFFER_CAPACITIES,
    THRESHOLD_EXPERIMENTS,
    ExperimentConfig,
    ReplicationResult,
    Scenario,
    run_experiment,
    s1_experiment,
    s2_experiment,
    s3_experiment,
    s4_experiment,
    transient_series,
)
from takt.plots import buffer_figure, signal_figure, threshold_figure

RESULTS_DIR = Path("results")
FIGURES_DIR = Path("docs/figures")
WARMUP_BIN_H = 12.0
WARMUP_WINDOW_BINS = 5
WARMUP_CHECK_LENGTH_H = 10_080.0

type Adjust = Callable[[ExperimentConfig], ExperimentConfig]


def _write_definition(config: ExperimentConfig, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "definition.json").write_text(
        json.dumps(dataclasses.asdict(config), indent=2, default=str) + "\n"
    )


def _run(name: str, out: Path, workers: int, threshold: float | None) -> None:
    if name in THRESHOLD_EXPERIMENTS:
        if threshold is None:
            raise SystemExit(f"{name} needs --threshold, the alarm threshold of the setting")
        config = THRESHOLD_EXPERIMENTS[name](threshold)
    else:
        config = EXPERIMENTS[name]()
    results = run_experiment(config, workers)
    folder = out / config.name
    folder.mkdir(parents=True, exist_ok=True)
    replication_table(results).to_csv(folder / "replications.csv", index=False)
    summary = summary_table(results)
    summary.to_csv(folder / "summary.csv", index=False)
    _write_definition(config, folder)
    print(summary.to_string(index=False))


def _validate(figures: Path, workers: int, adjust: Adjust = lambda c: c) -> None:
    """Run S1 as the reference case and after the warm-up and compare with the paper."""
    figures.mkdir(parents=True, exist_ok=True)
    comparisons, summaries = [], []
    for name in ("s1-from-start", "s1"):
        results = run_experiment(adjust(EXPERIMENTS[name]()), workers)
        comparisons.append(compare_with_published(results).assign(variant=name))
        summaries.append(summary_table(results).assign(variant=name))
    comparison = pd.concat(comparisons, ignore_index=True)
    comparison.to_csv(figures / "validation-s1.csv", index=False)
    pd.concat(summaries, ignore_index=True).to_csv(
        figures / "validation-s1-summary.csv", index=False
    )
    print(comparison.to_string(index=False))


def _decompose(figures: Path) -> None:
    """Decompose the published monitoring rows and write the table (ADR-0016)."""
    figures.mkdir(parents=True, exist_ok=True)
    table = decompose_published_monitoring()
    table.to_csv(figures / "published-monitoring-decomposition.csv", index=False)
    print(table.to_string(index=False))


def _transient_check(
    items: Sequence[tuple[str, Scenario, float]],
    seed: int,
    replications: int,
    workers: int,
    length_h: float,
) -> tuple[pd.DataFrame, dict[str, dict[str, tuple[float, ...]]]]:
    """Find the truncation point of every scenario by the marginal standard error rule.

    Each item is an experiment name, a scenario, and the warm-up period that the
    experiment uses, against which the truncation point is compared.
    """
    rows = []
    curves: dict[str, dict[str, tuple[float, ...]]] = {}
    for experiment, scenario, warmup_in_use_h in items:
        outputs, wips = transient_series(
            scenario, seed, replications, length_h, WARMUP_BIN_H, workers
        )
        curves[scenario.name] = {}
        for series_name, series in (("parts_per_bin", outputs), ("wip_per_bin", wips)):
            result = welch(series, WARMUP_WINDOW_BINS)
            truncation_h = mser_truncation(result.averaged) * WARMUP_BIN_H
            curves[scenario.name][series_name] = result.smoothed
            rows.append(
                {
                    "experiment": experiment,
                    "scenario": scenario.name,
                    "series": series_name,
                    "plateau_mean": result.plateau_mean,
                    "mser_truncation_h": truncation_h,
                    "warmup_in_use_h": warmup_in_use_h,
                    "exceeds_warmup_in_use": truncation_h > warmup_in_use_h,
                    "replications": replications,
                    "bin_h": WARMUP_BIN_H,
                }
            )
    return pd.DataFrame(rows), curves


def _warmup(out: Path, workers: int) -> None:
    """Analyse the initial transient of S1, the basis of ADR-0011."""
    config = s1_experiment()
    items = [(config.name, scenario, config.warmup_h) for scenario in config.scenarios]
    table, curves = _transient_check(
        items, config.seed, config.replications, workers, WARMUP_CHECK_LENGTH_H
    )
    folder = out / "warmup"
    folder.mkdir(parents=True, exist_ok=True)
    for scenario, series in curves.items():
        for name, smoothed in series.items():
            pd.DataFrame({"smoothed": smoothed}).to_csv(
                folder / f"{scenario}-{name}.csv", index_label="bin"
            )
    print(table.to_string(index=False))


def _published_comparison(results: Sequence[ReplicationResult]) -> pd.DataFrame:
    """Compare every S2 scenario with the published perfect monitoring system.

    The paper gives the setting with the highest quality and not its
    threshold, so no scenario is singled out as its counterpart, and the one
    with the highest mean quality in the model is marked (ADR-0015).
    """
    table = replication_table(results)
    quality_best = table.groupby("scenario", sort=False)["mean_quality"].mean().idxmax()
    frames = []
    for scenario in dict.fromkeys(r.scenario for r in results):
        own = [r for r in results if r.scenario == scenario]
        frames.append(
            compare_with_published(own, PUBLISHED_C1_PERFECT_MONITORING).assign(
                scenario=scenario, highest_quality=scenario == quality_best
            )
        )
    return pd.concat(frames, ignore_index=True)


def _all(figures: Path, out: Path, workers: int, adjust: Adjust = lambda c: c) -> None:
    """Run every experiment and write every table and figure of the report.

    The threshold of S3 and S4 is the S2 setting with the highest output
    (ADR-0015). Implements FR13.
    """
    started = time.perf_counter()
    figures.mkdir(parents=True, exist_ok=True)

    def run(config: ExperimentConfig) -> list[ReplicationResult]:
        config = adjust(config)
        _write_definition(config, out / config.name)
        results = run_experiment(config, workers)
        replication_table(results).to_csv(out / config.name / "replications.csv", index=False)
        print(f"{config.name}: {len(results)} replications, {time.perf_counter() - started:.0f} s")
        return results

    _validate(figures, workers, adjust)
    _decompose(figures)
    summary_table(run(EXPERIMENTS["s0"]())).to_csv(figures / "s0-summary.csv", index=False)
    s1 = run(EXPERIMENTS["s1"]())
    s1_summary = summary_table(s1)
    s1_summary.to_csv(figures / "s1-summary.csv", index=False)

    s2 = run(EXPERIMENTS["s2"]())
    s2_summary = summary_table(s2)
    s2_summary.to_csv(figures / "s2-summary.csv", index=False)
    difference_table(s2, s1, "S1").to_csv(figures / "s2-vs-s1.csv", index=False)
    _published_comparison(s2).to_csv(figures / "s2-vs-published.csv", index=False)
    threshold_figure(s2_summary, s1_summary, figures / "s2-threshold")
    best = best_scenario(s2_summary, "parts_produced")
    threshold = float(s2_summary[s2_summary["scenario"] == best]["setting_alarm_threshold"].iloc[0])
    print(f"setting of S3 and S4: {best}")

    s3 = run(THRESHOLD_EXPERIMENTS["s3"](threshold))
    s3_summary = summary_table(s3)
    s3_summary.to_csv(figures / "s3-summary.csv", index=False)
    difference_table(s3, s1, "S1").to_csv(figures / "s3-vs-s1.csv", index=False)
    signal_figure(s3_summary, figures / "s3-signal")

    s4 = run(THRESHOLD_EXPERIMENTS["s4"](threshold))
    s4_summary = summary_table(s4)
    s4_summary.to_csv(figures / "s4-summary.csv", index=False)
    pairs = [
        (f"S4 condition-based capacity {c}", f"S4 run-to-failure capacity {c}")
        for c in S4_BUFFER_CAPACITIES
    ]
    paired_table(s4, s4, pairs).to_csv(
        figures / "s4-condition-based-vs-run-to-failure.csv", index=False
    )
    buffer_figure(s4_summary, figures / "s4-buffer")

    check_config = adjust(s1_experiment())
    table, _ = _transient_check(
        _transient_items(threshold),
        check_config.seed,
        check_config.replications,
        workers,
        min(WARMUP_CHECK_LENGTH_H, check_config.warmup_h + check_config.run_length_h),
    )
    table.to_csv(figures / "warmup-check.csv", index=False)
    print(table.to_string(index=False))
    print(f"total: {time.perf_counter() - started:.0f} s with {workers} workers")


def _transient_items(threshold: float) -> list[tuple[str, Scenario, float]]:
    """The scenarios whose initial transient is checked against the warm-up in use.

    S1, the lowest and the highest threshold of S2, the worst signal of S3, and
    both policies at the reference capacity and at the two extreme capacities
    of S4.
    """
    s2 = s2_experiment()
    s3 = s3_experiment(threshold)
    s4 = s4_experiment(threshold)
    wanted = {
        s1_experiment().name: ["S1"],
        s2.name: [s2.scenarios[0].name, s2.scenarios[-1].name],
        s3.name: [s3.scenarios[-1].name],
        s4.name: [
            f"S4 {policy} capacity {capacity}"
            for policy in ("run-to-failure", "condition-based")
            for capacity in (10, 0, 20)
        ],
    }
    configs = {c.name: c for c in (s1_experiment(), s2, s3, s4)}
    items = []
    for name, scenario_names in wanted.items():
        by_name = {s.name: s for s in configs[name].scenarios}
        items.extend((name, by_name[n], configs[name].warmup_h) for n in scenario_names)
    return items


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line and run the chosen command."""
    parser = argparse.ArgumentParser(prog="takt", description=__doc__)
    parser.add_argument("--out", type=Path, default=RESULTS_DIR, help="folder for raw output")
    parser.add_argument(
        "--workers",
        type=int,
        default=os.cpu_count() or 1,
        help="processes for the replications, the results do not depend on it",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a named experiment and write its tables")
    run.add_argument("experiment", choices=sorted([*EXPERIMENTS, *THRESHOLD_EXPERIMENTS]))
    run.add_argument("--threshold", type=float, help="alarm threshold for s3 and s4")
    commands.add_parser("warmup", help="analyse the initial transient of scenario S1")
    for name, text in (
        ("validate", "compare S1 with the published results"),
        ("decompose", "decompose the published monitoring rows into two kinds of machine"),
        ("all", "run every experiment and write every table and figure of the report"),
    ):
        sub = commands.add_parser(name, help=text)
        sub.add_argument(
            "--figures", type=Path, default=FIGURES_DIR, help="folder for the committed files"
        )
    args = parser.parse_args(argv)
    if args.command == "run":
        _run(args.experiment, args.out, args.workers, args.threshold)
    elif args.command == "validate":
        _validate(args.figures, args.workers)
    elif args.command == "decompose":
        _decompose(args.figures)
    elif args.command == "all":
        _all(args.figures, args.out, args.workers)
    else:
        _warmup(args.out, args.workers)
