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

