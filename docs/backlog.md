# Backlog

The work queue. Items are taken one at a time and in order unless a
dependency says otherwise. Each item names its scope, the condition under
which it counts as done, and the documents that have to be updated in the same
change.

Status values: open, in progress, done.

---

## B0: Repository and project set up

Status: done.

Scope: create the Python project with locked dependencies, configure the
static checks, the test runner, and continuous integration, and create the
documents in `docs/`.

Done when: the dependencies install from the lock file, the checks and the
test suite pass, and the documents exist.

Documents to update: `dev-journal.md`, `decision-log.md`.

---

## B1: Reference case and conceptual model

Status: done.

Scope: fix the reference case and every parameter of the model with its unit
and its source or the statement that it is an assumption. Describe the
conceptual model before any model code is written: the entities, the states of
a machine, the events, and the assumptions. Draw the process flow of the line
and the state diagram of a machine. No model code.

Done when: `concept.md` no longer lists open points, the parameter table
exists, both diagrams render without errors, and the requirement draft is
revised against the case.

Documents to update: `concept.md`, `requirements.md`, `diagrams/README.md`,
`decision-log.md`, `dev-journal.md`.

---

## B2: Line without degradation

Status: done.

Scope: the configuration as immutable data with the parameters of the
reference case as its default, the machines with their cycle times, the
buffers with limited capacity, the source, and the sink. Blocking and
starvation follow from the buffers. Scenario S0.

Done when: the line produces exactly the output that follows from the cycle
times and the run length, blocking and starvation are covered by tests with
unequal cycle times, and two runs with the same seed are identical.

Documents to update: `requirements.md` (FR1, FR2, NFR1, NFR4, NFR5),
`dev-journal.md`.

---

## B3: Degradation, failure, and corrective repair

Status: done.

Scope: the health indicator with its random degradation events, the failure
at a health of zero with the scrapped part, the maintainers with their queue
of work orders, and the corrective repair. Scenario S1.

Done when: the health of a machine passes through its nine values in order, a
failed machine scraps its part and accepts no further one, a fourth
simultaneous failure waits for a free maintainer, and the random number
streams of the machines are independent of each other.

Documents to update: `requirements.md` (FR3, FR4, FR5), `diagrams/README.md`
if the state diagram changes, `decision-log.md`, `dev-journal.md`.

---

## B4: Indicators and experiment runner

Status: done.

Scope: the product quality of a part, the recording of all performance
indicators, independent replications, confidence intervals, and common random
numbers across scenarios. A command that runs an experiment and writes the
results as tables.

Done when: the indicators of the deterministic line are exact, a part that
passes six healthy machines has a quality of one, the treatment of the start
of a run is decided from a recorded analysis and not by feel, and an
experiment can be repeated from its definition alone.

Documents to update: `requirements.md` (FR9, FR10, FR11, FR12),
`decision-log.md`, `dev-journal.md`.

---

## B5: Verification and validation

Status: done.

Scope: verify the model against the exact values of S0 and against the
analytic availability and repair count in `concept.md`. Validate S1 against
the published results of the reference case with its run length and number of
replications. Check the conservation of parts and the extreme cases: a buffer
of capacity zero, a very large buffer, and a single maintainer. Examine each
assumption A1 to A9 for its influence on the comparison.

Done when: every check is an automated test or a recorded comparison, each
deviation from the published values is explained or recorded as a limit, and
the limits of the validation are written down for the report.

Documents to update: `requirements.md` (NFR2, NFR3), `dev-journal.md`.

---

## B6: Condition-based maintenance

Status: open.

Scope: the monitoring system with its sensing interval and alarm threshold,
the preventive repair with its health dependent duration, and the signal
quality with missed alarms and false alarms. Scenarios S2 and S3.

Done when: an ideal signal with a threshold below the smallest health value
reproduces S1 exactly, a signal that never raises an alarm does the same, a
machine with a pending work order keeps producing until the maintainer
arrives, a machine that fails while waiting receives the corrective repair,
and a false alarm causes a repair of a healthy machine.

Documents to update: `requirements.md` (FR6, FR7, FR8), `diagrams/README.md`,
`decision-log.md`, `dev-journal.md`.

---

## B7: Experiments and results

Status: open.

Scope: define and run the scenarios S0 to S4, including the variation of the
alarm threshold, the signal quality, and the buffer capacity. Generate the
tables and figures for the report.

Done when: every figure and table in `docs/figures/` is produced by one
command from the experiment definitions, and the runtime meets NFR6.

Documents to update: `requirements.md` (FR13, NFR6), `dev-journal.md`.

---

## B8: Structure diagrams and final review

Status: open.

Scope: the component diagram of the package and the sequence of one
replication, drawn from the implemented code. Give every requirement a final
status, repeat the complete set of experiments from a fresh clone, and record
the size of the implementation.

Done when: the diagrams match the code, `requirements.md` reflects reality,
and the fresh clone reproduces the committed figures.

Documents to update: `requirements.md`, `diagrams/README.md`, `README.md`,
`dev-journal.md`.
