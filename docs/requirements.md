# Requirements

This document lists the requirements of the simulation model and traces each
one to the code and the tests that satisfy it. It is the working basis for the
description of the model in the report and for the evaluation of the result. A
requirement is only marked as done when it is implemented and covered by a
test or, for a figure, by the generated file.

The requirement set was revised in B1 against the reference case in
`concept.md`. Every later change is recorded in `dev-journal.md`.

Status values: open, in progress, done, partly met, deferred. A deferred
requirement is specified on purpose but not implemented, and the reason is
stated next to it.

## Functional requirements

| ID | Requirement | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| FR1 | The model represents a serial line of a configurable number of machines with a cycle time per machine, a source with an arrival rate, and a sink. | open | | |
| FR2 | A buffer of limited capacity lies between two neighbouring machines, so that a machine can be blocked by a full buffer and starved by an empty one. | open | | |
| FR3 | Every machine has a health indicator that is lowered by a fixed step at random intervals drawn from a Weibull distribution with parameters per machine. | open | | |
| FR4 | A machine whose health reaches zero fails, scraps the part in process, and stays unavailable until a corrective repair has restored it to full health. | open | | |
| FR5 | Repairs are carried out by a limited number of maintainers, and work orders wait in the order of their creation. | open | | |
| FR6 | The repair time depends on the health of the machine at the start of the repair, in the three classes of the reference case. | open | | |
| FR7 | Under condition-based maintenance a monitoring system reads the health of every machine at a fixed interval and creates a work order at or below an alarm threshold. The machine produces until the maintainer arrives. | open | | |
| FR8 | The quality of the sensor signal is configurable through the probability that a reading at or below the threshold raises an alarm and the probability that a reading above it raises a false alarm. | open | | |
| FR9 | Every machine adds its share of quality to a part in proportion to its health at the time of processing. | open | | |
| FR10 | The model records the performance indicators listed in `concept.md`. | open | | |
| FR11 | An experiment runs a scenario in several independent replications and reports means with confidence intervals. | open | | |
| FR12 | The scenarios of an experiment use common random numbers, so that they are compared under identical conditions. | open | | |
| FR13 | The results are written as tables and figures that the report can use directly. | open | | |
| FR14 | A periodic inspection policy inspects every machine at a fixed interval and orders a repair below a health threshold. | deferred | | |
| FR15 | The model supports configurations with parallel machines and several part paths. | deferred | | |

FR14 and FR15 belong to the reference case but not to the questions of this
project. They are specified so that the limits of the model are explicit, and
they are deferred because the length of the report favours one configuration
examined in depth over five examined superficially.

## Nonfunctional requirements

| ID | Requirement | Status | Implemented in | Verified by |
| --- | --- | --- | --- | --- |
| NFR1 | Reproducibility: a run with the same parameters and the same seed produces the same result. | open | | |
| NFR2 | Verification: without degradation the model produces the exact output of a deterministic line, and under the run-to-failure policy the availability and the repair count of a machine match the analytic values in `concept.md` within the confidence interval. | open | | |
| NFR3 | Validation: under the run-to-failure policy the model is compared with the published results of the reference case, and every deviation is explained or recorded as a limit. | open | | |
| NFR4 | Transparency: every parameter is defined in one place, with its unit and its source or the statement that it is an assumption. | open | | |
| NFR5 | Testability: the rules of the model are covered by automated tests that run without generating figures. | open | | |
| NFR6 | Performance: the complete set of experiments runs in under ten minutes on a current notebook. | open | | |
| NFR7 | Maintainability: static checks and the code style check pass without exceptions. | done | `pyproject.toml`, `.github/workflows/tests.yml` | `uv run ruff check`, `uv run ruff format --check` |
