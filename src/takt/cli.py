"""Command line entry point: runs experiments and the warm-up analysis."""

import argparse
import dataclasses
import json
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from takt.analysis import mser_truncation, replication_table, summary_table, welch
from takt.config import RunConfig
from takt.experiment import (
    EXPERIMENTS,
    binned_series,
    replication_seeds,
    run_experiment,
    s1_experiment,
)
from takt.model import run_line

RESULTS_DIR = Path("results")
WARMUP_BIN_H = 12.0
WARMUP_WINDOW_BINS = 5


def _run(name: str, out: Path) -> None:
    config = EXPERIMENTS[name]()
    results = run_experiment(config)
    folder = out / config.name
    folder.mkdir(parents=True, exist_ok=True)
    replication_table(results).to_csv(folder / "replications.csv", index=False)
    summary = summary_table(results)
    summary.to_csv(folder / "summary.csv", index=False)
    (folder / "definition.json").write_text(
        json.dumps(dataclasses.asdict(config), indent=2, default=str) + "\n"
    )
    print(summary.to_string(index=False))


def _warmup(out: Path) -> None:
    config = s1_experiment()
    scenario = config.scenarios[0]
    total_h = config.run_length_h
    outputs, wips = [], []
    for seed in replication_seeds(config.seed, config.replications):
        raw = run_line(scenario.line, RunConfig(run_length_h=total_h, seed=seed))
        output, wip = binned_series(raw, WARMUP_BIN_H)
        outputs.append(output)
        wips.append(wip)
    rows = []
    folder = out / "warmup"
    folder.mkdir(parents=True, exist_ok=True)
    for name, series in (("parts_per_bin", outputs), ("wip_per_bin", wips)):
        result = welch(series, WARMUP_WINDOW_BINS)
        truncation = mser_truncation(result.averaged)
        rows.append(
            {
                "series": name,
                "plateau_mean": result.plateau_mean,
                "mser_truncation_bin": truncation,
                "mser_truncation_h": truncation * WARMUP_BIN_H,
            }
        )
        pd.DataFrame(
            {"averaged": result.averaged[: len(result.smoothed)], "smoothed": result.smoothed}
        ).to_csv(folder / f"{name}.csv", index_label="bin")
    print(pd.DataFrame(rows).to_string(index=False))


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the command line and run the chosen command."""
    parser = argparse.ArgumentParser(prog="takt", description=__doc__)
    parser.add_argument("--out", type=Path, default=RESULTS_DIR, help="folder for raw output")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a named experiment and write its tables")
    run.add_argument("experiment", choices=sorted(EXPERIMENTS))
    commands.add_parser("warmup", help="analyse the initial transient of scenario S1")
    args = parser.parse_args(argv)
    if args.command == "run":
        _run(args.experiment, args.out)
    else:
        _warmup(args.out)
