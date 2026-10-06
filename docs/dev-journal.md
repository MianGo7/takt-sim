# Development journal

The chronological record of the work. It is the main source for the
description of the process and for the critical reflection in the report, so
problems are recorded as they happened, including the ones that turned out to
be the author's own mistakes.

Template for every entry:

    ## YYYY-MM-DD

    **Worked on.** What was done, with backlog item ids.

    **Decisions.** What was decided and why, with ADR numbers where one exists.

    **Problems.** What went wrong, how it was noticed and how it was solved.

    **Next.** What comes next.

---

## 2026-10-06

**Worked on.** Selection of the examination task, set up of the repository,
and the conceptual model, backlog items B0 and B1. Of the three tasks offered,
Task 3 was chosen, which asks for a simulation model of a part of a smart
factory with a stated purpose and a detailed description of the results. The
two other tasks, a process model in the Business Process Model and Notation
(BPMN) and a value stream analysis, end in a diagram and a qualitative
assessment, whereas a simulation yields measured values for a present state
and for alternatives, which gives the evaluation a quantitative basis. The
project was created with locked dependencies, static checks, a test runner,
and a continuous integration workflow.

For B1, the literature was searched for a production line with published
parameters. The serial configuration of Dadfarnia et al. (2023) was chosen as
the reference case, its parameters were collected with page references, and
the points the paper leaves open were written down as the assumptions A1 to
A8. The conceptual model, the scenarios S0 to S4, and the performance
indicators are fixed in `concept.md`, the requirements were revised against
the case, and the layout of the line and the state diagram of a machine were
drawn and rendered.

**Decisions.** The model is written in Python with SimPy instead of one of the
two tools named in the task (ADR-0001). The project uses Python 3.13 with uv
and the scientific Python libraries (ADR-0002), Ruff and pytest with
continuous integration (ADR-0003), and PlantUML sources for the diagrams
(ADR-0004). The reference case is taken from a published simulation study
(ADR-0005). The scope is one configuration and two policies, with the signal
quality expressed through two error rates (ADR-0006), and the model adopts the
time unit and the terms of the reference case (ADR-0007).

**Problems.** The first draft of the concept assumed a generic line of three
or four stations that fail at random and are repaired. The reference case
models something different: a health indicator that falls in steps until the
machine fails, and a repair time that depends on the health at the start of
the repair. The draft was discarded and the concept rewritten around the
case, because a model that only resembles its source cannot be validated
against it.

The paper does not state the unit of the Weibull scale parameter and
describes the degradation as tied to the use of a machine, which left two
readings open. They were resolved before any code was written by deriving the
availability and the repair count of a machine analytically for the
run-to-failure policy. With the scale in hours and degradation in clock time,
the derivation gives a mean availability of 77.0 percent and 115.9 repairs per
machine, against published values of 76.70 percent and 115.12. The standard
deviations across the six machines match as well. The reading is therefore
recorded as the assumptions A1 and A2, and the derived values serve as targets
for the verification in B5.

One risk is recorded: the task lists graphical simulation tools as standard
software, and a model written in code has no animation that makes its
correctness plausible at a glance. The verification and validation in B5 are
the answer to that risk and therefore cannot be shortened if time becomes
scarce. A second risk concerns the published results for the perfect
monitoring system, which are reported only for an alarm setting that the paper
does not state. They may not be reproducible, which is why the validation
rests on the run-to-failure policy.

**Next.** B2, the line without degradation.

## 2026-10-06 (second entry)

**Worked on.** Backlog item B2, the line without degradation. The
configuration is implemented as frozen dataclasses with the parameters of the
reference case as defaults and with validation on construction. The model
consists of a source, machines with a constant cycle time, buffers of limited
capacity, and a sink. Blocking and starvation are not coded as states: a
machine that cannot hand over its finished part waits on the full buffer and
holds the part, and a machine without a part waits on the empty one. The
tests compare with equality: the S0 output of 10,074 parts, the first part at
6 hours, a slow last machine that fills its buffer and blocks the machine
before it, a slow first machine and a slow source that starve the machines
behind them, the output limit of the slowest machine, the conservation of
parts, and the identity of two runs with the same seed. The suite has 26 tests
and passes together with the static checks.

**Decisions.** The run covers the half-open interval up to the run length,
which is the default of SimPy (ADR-0008). The modules stay single files, and
the seed and one generator per machine exist from the start (ADR-0009). The
source is modelled as a supplier that the first machine pulls from, with the
next offer one interval after the previous part was taken, which is the
reading of A7 that loses no part and adds no hidden buffer in front of the
line.

**Problems.** The expected output of one test, a line with a machine of 3
hours, was first written down as 98 parts and the model returned 99. The
completions fall at 5 + 3k hours, and the last one before 300 hours is k = 98,
so 99 is correct and the expectation was a miscount. The test was corrected
after deriving the value, not after seeing the model output alone. A second
point is a limit: a buffer capacity of zero is rejected by the configuration,
because a store of capacity zero does not exist in SimPy. The extreme case
belongs to B5 and needs a rendezvous between two machines.

**Next.** B3, degradation, failure, and corrective repair.


## 2026-10-06 (third entry)

**Worked on.** Backlog item B3, degradation, failure, and corrective repair.
The configuration gained the Weibull parameters per machine, the number of
maintainers, and the corrective repair time, all from the parameter table, and
a function that builds the reference line with degradation for scenario S1. A
machine without degradation settings never degrades, so that S0 keeps its
exact output. In the model, a second process per machine draws the intervals
between degradation events and lowers the health in steps of one eighth, the
failure scraps the part in process, and a pool of three maintainers repairs
the failed machines for 20 hours in the order of the failures. The tests cover
the nine health values in order, the restoration of the health, the scrapped
part, the refusal of parts during the repair, a machine that fails while
starved and one that fails while blocked, the wait of a fourth simultaneous
failure and the order of service, the conservation of parts, and the
independence of the streams. The suite has 46 tests and passes together with
the static checks. A plausibility run of S1 over ten seeds gave about 93 to 94
repairs for each regular machine and 221 for M3, close to the analytic values
of 94.5 and 222.8. It was not recorded as a result, because the verification
with confidence intervals belongs to B5.

**Decisions.** A failure interrupts the process of a machine through SimPy and
does not rely on a check at the start of the cycle, which would let a failed
machine finish a part or take one during its repair. A machine that is blocked
hands over its finished part before it waits for the repair, and a starved
machine takes no part. The reference case is silent on both, and the reading
is the new assumption A9. The health is an integer step count. The streams
are one record per machine with one generator per source, and the stream of a
machine depends on the seed and its position only (ADR-0010).

**Problems.** The first run of the new tests failed in four places, and all
four were errors in the expectations. After a repair the degradation starts
again at once, so a second failure fell inside the window of three tests and
the count of repairs and scrapped parts was higher than written down. The
expectation of the starved machine used the wrong index of the completion
list. The tests were corrected by working out the failure and repair times
first. A limit remains: the tie between a failure and a handover of a part at
the same instant is resolved in favour of the failure and is not exercised by
a test, because it has probability zero with continuous Weibull intervals.

**Next.** B4, indicators and the experiment runner.

## 2026-10-06 (fourth entry)

**Worked on.** Backlog item B4, indicators and the experiment runner. The
model now records raw traces: the completed parts with lead time and quality,
the times of scrapped parts, the level of every buffer, the state of every
machine, and the repairs. Every part carries the sum of the health values of
the machines that finished it, and the sink divides it by the number of
machines, so that a part from six healthy machines has a quality of exactly
one. The new `experiment` module defines scenarios and experiments in code,
derives one seed per replication that is shared by all scenarios, and reduces
each run to the indicators of the observation window. The new `analysis`
module computes t-based 95 percent confidence intervals, the summary and
replication tables, the Welch moving average, and the marginal standard error
rule. The command `uv run python -m takt run s0` or `run s1` writes the two
tables and the definition of the experiment as JSON to `results/`. The suite
has 79 tests and passes together with the static checks. The tests compare
the indicators of the deterministic line with equality, check the interval
against a table value and by its coverage over 2,000 samples, and show that
two scenarios that differ only in the buffers have identical machine
availability in every replication.

**Decisions.** The warm-up period is 252 hours, decided from the analysis of
S1 with `uv run python -m takt warmup`: 50 replications, root seed 2026, run
of 10,080 hours, bins of 12 hours, run on the working tree of this item on top
of commit ffceb44. The marginal standard error rule gave 252 hours for the
output per bin and 132 hours for the work in progress per bin, and the larger
value was taken. The averaged work in progress overshoots to 24.7 parts in
the bin from 108 to 120 hours against a plateau of 21.9, which is the visible
sign of a line that starts empty with all machines new. The reading of the
health for the quality, at the end of the cycle, is the new assumption A10.
The rejected alternatives are in ADR-0011.

**Problems.** The first rule for the truncation point, a relative tolerance
around the plateau of the smoothed series, did not work. The result moved
from 36 hours to over 9,000 hours when the tolerance was changed from ten to
five percent, because the smoothed series of 50 replications still fluctuates
by more than the tolerance. The rule was replaced before any value was used,
and the failed attempt is recorded in ADR-0011. A second correction concerned
the documents: a script that edited several files stopped at its second edit,
after the first had been applied, and the remaining edits were redone, so the
record was checked against the files before it was trusted. A limit that
follows from the design is that the common random numbers hold only in part
once a preventive repair shifts the degradation events of a machine (B6).
S1 over 50 replications takes about six seconds, and the warm-up analysis
about 40 seconds. A first run of S1 was made to check that the command works.
Its values are not recorded here, because the comparison with the published
results belongs to B5 and is made there with its own run.

**Next.** B5, verification and validation.
