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
| FR1 | The model represents a serial line of a configurable number of machines with a cycle time per machine, a source with an arrival rate, and a sink. | done | `config.py` (`MachineConfig`, `LineConfig`), `model.py` (`Source`, `Machine`, `Sink`, `Line`) | `tests/test_line.py`, `tests/test_config.py` |
| FR2 | A buffer of limited capacity lies between two neighbouring machines, so that a machine can be blocked by a full buffer and starved by an empty one. | done | `config.py` (`BufferConfig`), `model.py` (`Buffer`, `Handoff`, ADR-0012) | `tests/test_line.py`: blocking by a full buffer, starvation by an empty one. `tests/test_verification.py`: capacity zero, a very large buffer |
| FR3 | Every machine has a health indicator that is lowered by a fixed step at random intervals drawn from a Weibull distribution with parameters per machine. | done | `config.py` (`DegradationConfig`, `reference_line_with_degradation`), `model.py` (`Machine`, `MachineStreams`) | `tests/test_degradation.py`: the nine health values in order, independent streams, the health history of a machine unchanged when another machine is altered. The agreement of the distribution with the analytic availability is checked in B5 |
| FR4 | A machine whose health reaches zero fails, scraps the part in process, and stays unavailable until a corrective repair has restored it to full health. | done | `model.py` (`Machine`, `Maintainers`, ADR-0010, A9) | `tests/test_degradation.py`: scrapped part, no part accepted during the repair, starved and blocked machines, restoration of the health |
| FR5 | Repairs are carried out by a limited number of maintainers, and work orders wait in the order of their creation. | done | `config.py` (`RepairConfig`), `model.py` (`Maintainers`, `RepairRecord`) | `tests/test_degradation.py`: a fourth simultaneous failure waits for the first free maintainer, work orders start in the order of creation |
| FR6 | The repair time depends on the health of the machine at the start of the repair, in the three classes of the reference case. | open | | |
| FR7 | Under condition-based maintenance a monitoring system reads the health of every machine at a fixed interval and creates a work order at or below an alarm threshold. The machine produces until the maintainer arrives. | open | | |
| FR8 | The quality of the sensor signal is configurable through the probability that a reading at or below the threshold raises an alarm and the probability that a reading above it raises a false alarm. | open | | |
| FR9 | Every machine adds its share of quality to a part in proportion to its health at the time of processing. | done | `model.py` (`Part`, `CompletedPart`, `Machine`, `Sink`), ADR-0011, A10 | `tests/test_indicators.py`: a part through six healthy machines has a quality of one, and the share follows the health at the end of the cycle |
| FR10 | The model records the performance indicators listed in `concept.md`. | done | `experiment.py` (`line_indicators`, `LineIndicators`, `MachineIndicators`), `model.py` (traces in `LineResult`) | `tests/test_indicators.py`: exact values for the deterministic line, the window, and the time shares. The agreement of S1 with the published values is checked in B5 |
| FR11 | An experiment runs a scenario in several independent replications and reports means with confidence intervals. | done | `experiment.py` (`run_experiment`), `analysis.py` (`estimate`, `summary_table`), `cli.py` | `tests/test_analysis.py`: interval against a table value and coverage of about 95 percent. `tests/test_experiment.py`: repetition from the definition and the written tables |
| FR12 | The scenarios of an experiment use common random numbers, so that they are compared under identical conditions. | done | `experiment.py` (`replication_seeds`) | `tests/test_experiment.py`: equal seeds across scenarios and identical availability for scenarios that differ only in the buffers |
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
| NFR1 | Reproducibility: a run with the same parameters and the same seed produces the same result. | partly met | `config.py` (`RunConfig`), `model.py` (`spawn_machine_streams`, `run_line`) | `tests/test_line.py`: same seed, identical result. Informative from B3: `tests/test_degradation.py` repeats it with degradation, and runs with different seeds differ |
| NFR2 | Verification: without degradation the model produces the exact output of a deterministic line, and under the run-to-failure policy the availability and the repair count of a machine match the analytic values in `concept.md` within the confidence interval. | done | `tests/test_verification.py`, `tests/test_indicators.py`, `experiment.py` | Exact values of S0 in `tests/test_indicators.py`. Single machines with the parameters of M1 and M3 against the analytic availability and repair count, with a tolerance of four standard errors of 100 replications, recorded deviations below 1.7 standard errors (ADR-0013). Exact accounting of released, produced, scrapped, and held parts, the extreme cases, and the limits of the maintainers |
| NFR3 | Validation: under the run-to-failure policy the model is compared with the published results of the reference case, and every deviation is explained or recorded as a limit. | done | `analysis.py` (`compare_with_published`), `cli.py` (`validate`) | `docs/figures/validation-s1.csv` and `validation-s1-summary.csv`, ADR-0013. The deviations and the limits of the validation are in the journal entry of 2026-10-06 (fifth entry) |
| NFR4 | Transparency: every parameter is defined in one place, with its unit and its source or the statement that it is an assumption. | partly met | `config.py` | `tests/test_config.py`: defaults equal the parameter table in `concept.md`. The monitoring parameters follow in B6 |
| NFR5 | Testability: the rules of the model are covered by automated tests that run without generating figures. | done | `tests/` | `uv run pytest`: the model tests run without files and without Matplotlib |
| NFR6 | Performance: the complete set of experiments runs in under ten minutes on a current notebook. | open | | |
| NFR7 | Maintainability: static checks and the code style check pass without exceptions. | done | `pyproject.toml`, `.github/workflows/tests.yml` | `uv run ruff check`, `uv run ruff format --check` |
