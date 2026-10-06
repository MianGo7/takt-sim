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
