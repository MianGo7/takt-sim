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

    git clone <repository url>
    cd takt-sim
    uv sync

## Checks

    uv run pytest             # the test suite
    uv run ruff check         # static checks
    uv run ruff format --check   # code style

## Project structure

    src/takt/           the simulation package
    tests/              the test suite

    docs/
      concept.md        the reference case, its parameters, the assumptions, and the indicators
      requirements.md   requirements of the model with their status
      decision-log.md   tooling and modelling decisions with rejected alternatives
      dev-journal.md    chronological development record
      backlog.md        scoped work items, taken one at a time
      diagrams/         process and structure diagrams as PlantUML sources
      figures/          result figures and tables referred to by the report
