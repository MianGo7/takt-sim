# Takt

A discrete-event simulation of a small smart factory production line: six
milling machines in series with a buffer between two neighbouring machines.
The machines degrade over time and fail when their health is used up. The
model compares two maintenance policies, running the machines to failure and
condition-based maintenance, in which a monitoring system reads the health of
every machine and orders a short planned repair before the failure occurs.
Every policy is simulated under identical random conditions, and the effect is
measured in output, lead time, work in progress, availability, and product
quality.

The line and its parameters are taken from a published simulation study
(Dadfarnia et al., 2023), so that the model can be validated against
published results before it is extended.

This repository is the practical part of a project report for the IU course
DLBDSESF02, Smart Factory II.

- Course: DLBDSESF02, Smart Factory II
- Task: Task 3, manufacturing simulation of a smart factory
- Author: Mian Gohar Ehsan
- Matriculation number: IU14147184
- Submitted to: Qaadan, Sahar
- Type of Thesis: Project Report

## Purpose of the model

The simulation answers one question before any investment is made: at which
alarm threshold and at which quality of the sensor signal does condition
monitoring improve the output of the line, and what does it cost or gain in
product quality. The full concept, including the parameters, the assumptions,
and the performance indicators, is in `docs/concept.md`.

## Requirements

- Python 3.13
- uv, which creates the virtual environment and installs the locked
  dependencies

## Set up and run

    git clone https://github.com/MianGo7/takt-sim.git
    cd takt-sim
    uv sync

## Run the experiments

    uv run python -m takt all         # every table and figure of the report
    uv run python -m takt run s1      # one experiment, tables to results/s1
    uv run python -m takt run s4 --threshold 0.5
    uv run python -m takt validate    # S1 against the published results
    uv run python -m takt decompose   # the published monitoring rows by kind of machine
    uv run python -m takt warmup      # analysis of the initial transient of S1

The command `all` runs the scenarios S0 to S4 with 50 replications each, applies
the decomposition of the published monitoring rows, and writes the tables and
the figures to `docs/figures/`, and the raw replications
and the definition of every experiment to `results/`, which is not versioned.
The replications run in parallel, with `--workers` as the number of processes,
and the result does not depend on that number. The complete set takes about
40 seconds with 18 processes and 6 minutes and 43 seconds with one on the
machine of the author. A fresh clone with a new environment reproduces every
file in `docs/figures/` byte for byte.

## Checks

    uv run pytest             # the test suite
    uv run ruff check         # static checks
    uv run ruff format --check   # code style

## Project structure

    src/takt/           the simulation package
      config.py         parameters as frozen dataclasses
      model.py          machines, buffers, maintainers, and the two policies
      experiment.py     scenarios, replications, and indicators
      analysis.py       confidence intervals, paired differences, and warm-up analysis
      plots.py          the figures
      cli.py            the command line
    tests/              the test suite

    docs/
      concept.md        the reference case, its parameters, the assumptions, and the indicators
      requirements.md   requirements of the model with their status
      decision-log.md   tooling and modelling decisions with rejected alternatives
      dev-journal.md    chronological development record
      backlog.md        scoped work items, taken one at a time
      diagrams/         process and structure diagrams as PlantUML sources
      figures/          result figures and tables referred to by the report
