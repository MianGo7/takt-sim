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

## 2026-10-06 (fifth entry)

**Worked on.** Backlog item B5, verification and validation. For the
verification, single machines with the parameters of M1 and of M3 were run in
100 replications of 10,080 hours after a warm-up of 1,000 hours and compared
with the analytic availability and repair count derived from the Weibull and
gamma functions. The part accounting is now exact: the parts released by the
source equal the parts produced, scrapped, waiting in buffers, and held by
machines at every checked time, for buffer capacities of 0, 1, and 10 and three
seeds. The extreme cases are covered: a buffer of capacity zero, which needed a
new rendezvous link (ADR-0012), a very large buffer, one maintainer, and no more
than three simultaneous repairs with three maintainers. For the validation, S1
was run with 50 replications in two variants and compared with Table I of the
reference case on p. 421, with `uv run python -m takt validate`. The tables are
`docs/figures/validation-s1.csv` and `validation-s1-summary.csv`. The suite has
104 tests and passes together with the static checks.

**Decisions.** The criteria of the comparison are in ADR-0013 and the semantics
of a capacity of zero in ADR-0012. Two indicators were added because the
examination of the assumptions needs them: the spread of the part quality, and
the number of failures by what the machine was doing, which bounds the effect of
A9 without a second model.

**Results.** All values are from commit 920c183 with the changes of this item,
root seed 2026, 50 replications, 95 percent confidence level. The z values are
over the standard errors of the model and of the published mean. Only the one of
the number of parts rests on the published standard deviation of the
replications, the others use the spread of this model as a stand-in (ADR-0013).

| Indicator | Published | From time zero | After the warm-up |
| --- | --- | --- | --- |
| Availability, mean of six machines | 76.70 percent | 76.77 ± 0.05 (z 2.05) | 76.70 ± 0.05 (z -0.04) |
| Repairs per machine | 115.12 | 114.79 ± 0.25 (z -1.90) | 115.25 ± 0.23 (z 0.81) |
| Parts produced | 4,730.16 | 4,747.4 ± 15.1 (z 1.62) | 4,746.8 ± 15.3 (z 1.55) |
| Mean quality | 0.60 | 0.6033 ± 0.0010 | 0.6028 ± 0.0010 |

The spreads agree as well. The spread of the availability over machines is 0.0943
against 0.0948, that of the repairs 47.20 and 47.27 against 47.43, that of the
number of parts over replications 52.98 and 53.90 against 53.64, and that of the
part quality 0.1238 and 0.1231 against 0.123. The last agreement supports the
reading of the published spread of the quality as a spread over parts. The
verification gave z values of 1.60 and 1.65 for the availability and the repair
count of a regular machine and 1.23 and 1.20 for M3, all below two. The
simulated availability after the warm-up, 0.7670, also follows from the
analytic mean of six of 0.7701 and the share of 0.43 percent of the time that
failed machines wait for a maintainer: 0.7701 × (1 - 0.0043) = 0.7668.

**Deviations.** Three rows are not inside the confidence interval of the model
plus the rounding of the paper in the variant from time zero: the availability,
the repair count, and the number of parts. The repair count and the number of
parts have a z value below 1.96, and the availability, at 2.05 with a stand-in
standard error, lies marginally above it. In
the variant after the warm-up the availability and the repair count agree, and
the number of parts remains 17 above the published value, 0.35 percent. The
direction of the two variants is consistent with the initial transient: a line
with new machines has fewer failures in its first hours, so the whole run shows
a slightly higher availability and fewer repairs than the steady state. The
published values lie nearer to the steady state than to the whole run. Whether
the authors used a warm-up period or started their machines at another health
cannot be decided from the paper, and the deviation is recorded and not removed.

**Assumptions.** The influence of each on the comparison, from the run or from
a calculation, with the kind of evidence named.

- A1, from a calculation with the verified formula: a scale in days gives an
  availability of 0.990 for a regular machine and 0.968 for M3, a scale in
  minutes 0.067 and 0.021, against 0.767 published for the mean. Only hours is
  consistent.
- A2, from Table I: the availability of the five configurations under the run to
  failure lies between 76.66 and 76.70 percent while the number of parts lies
  between 4,730 and 7,218 (p. 421). A degradation that depends on the use of the
  machine would not give the same availability for such different utilisation.
- A3 to A5, not varied: a variant needs a random cycle time, a random repair
  time, and a noise term in the quality, none of which the paper quantifies. The
  availability and the repair count do not depend on the distribution of the
  repair time through the renewal argument, and the queue for maintainers is
  short, see A8. The match of the quality spread shows no sign of a missing noise
  term, but rests on the reading of that spread.
- A6, not relevant in S1: it concerns the preventive repair and matters from B6.
- A7, from the run: the first machine is never starved (share 0.0000) and is
  blocked for about 30 percent of the time, so the rule for the source does not
  affect S1.
- A8, from the run: a failed machine waits for a maintainer between 0.38 and 0.56
  percent of the time, so a different priority rule can act only on that share.
- A9, from the run: a run has about 418 failures of a machine in process, which
  equals the scrapped parts, 160 of a starved machine, and 112 of a blocked
  machine. The alternative reading, which scraps the finished part of a blocked
  machine, would remove at most 112 parts per run, 2.4 percent of the output. It
  is the largest identified sensitivity, and the deviation of 17 parts lies
  inside that bound, so the validation does not decide between the readings.
- A10, from a calculation, not simulated: reading the health at the start of the
  cycle raises the quality by about 0.0162, from the probability of a degradation
  event in a cycle of one hour per machine. That would give about 0.619 against
  0.60 published. The reading at the end of the cycle was fixed in the code
  before the first run of S1.

**Problems.** Two defects of this project were found. A test with one
maintainer showed machine states that summed to more than the run, because a
machine that failed while blocked stayed recorded as under repair after the
repair had ended, although it still held its finished part. This came from B4
and was corrected, and the machine is now recorded as blocked again at the end
of its repair. It overstated the downtime of those machines and so slightly
understated the availability indicator. The first run of S1 in B4 was not
recorded, and the warm-up analysis used the output and the work in progress,
which the defect does not touch. The first version of the count of failures by
state returned about 50 failures per run against about 690 repairs, because a
failure that meets a free maintainer goes to the repair at the same instant and
the wait of length zero is not in the trace. It was noticed by comparing with
the repairs and corrected, and a test now ties the failures in process to the
scrapped parts. The published sampling error is not known for three of the four
rows, which limits the z values to indicative ones.

**Limits of the validation.** One configuration and one policy are validated,
the serial line C1 under the run to failure, and the paper reports no other
policy that the model contains. The published run may have differed in the
treatment of the start, and the three assumptions A3 to A5 are not varied. The
z values of three rows use a stand-in for the published standard error. The
quality row is judged by the rounding of the paper. The validation therefore
supports the degradation, repair, and quality logic for the run to failure, and
it does not validate the condition-based policy, which has no published
counterpart in the model.

**Next.** B6, condition-based maintenance.

## 2026-10-06 (sixth entry)

**Worked on.** Backlog item B6, condition-based maintenance. The configuration
holds the policy as `RunToFailureConfig` or `ConditionBasedConfig` in the line,
with the alarm threshold, the sensing interval of one hour, and the detection
and false alarm probabilities, and the repair configuration now has the three
repair times by health class. In the model, a policy is an object with a common
interface. `ConditionBased` reads every machine once per interval and draws one
number per machine and reading from a new sensor stream. A machine has at most
one open work order, which the failure or an alarm creates, and the maintainers
serve the orders in the order of creation. The kind and duration of the repair
follow from the health at the start: 20 hours at zero, 5 hours below 0.5, and
2.5 hours from 0.5 upwards. A preventive repair pauses the part in process,
which resumes with its remaining cycle time. The indicators gained the
preventive repairs and the true and false alarms, and the count of failures by
state now comes from a record kept by the machine, because the state trace can
no longer tell a failure from the start of a preventive repair. The activity
diagram of the two policies is new, and the state diagram has a note on the
pause and on the naming of the repair state. The suite has 125 tests and passes
together with the static checks.

**Decisions.** The policy interface, the one order per machine, the rule that a
waiting order serves a failure, the pause of the part, and the draws of the
monitoring system are in ADR-0014, with the new assumptions A11 and A12 in
`concept.md`. The three variables of the extension are listed there as
scenario variables without a source.

**Checks.** An ideal signal with a threshold of zero and a signal that never
raises an alarm give exactly the raw output of S1 for three seeds, compared by
equality of the complete result. The validation tables of B5 were produced again
after the change. The comparison is unchanged, and the summary has the same
values for all existing rows and 18 new ones for the preventive repairs and the
alarms, all zero for S1. The tests also show that a machine with a pending order
keeps producing and is repaired when the maintainer is free, that a machine that
fails while its order waits receives the 20 hour repair at the place of its
order, that a false alarm repairs a healthy machine in 2.5 hours and scraps
nothing, that the share of readings that raise an alarm matches the two
probabilities within four standard deviations, and that every released part is
accounted for with preventive repairs and false alarms.

**Problems.** Four of the new tests failed at first, and the expectations were
wrong in each case. Three put an event of the degradation at an integer hour
that coincides with a reading of the monitoring system, so that the order of the
two decided the result, and the scales of the degradation were changed to avoid
the tie. Two of those three also looked for the record of a repair that had not
ended, because a repair is recorded only when it is complete. The fourth was a
wrong belief and not a slip of timing: the test assumed that the monitoring
lowers the availability, as in the perfect monitoring row of the reference case.
At a threshold of 0.5 the availability of the model is higher than under the run
to failure, because a repair of 2.5 or 5 hours replaces one of 20 hours. The
assertion had no basis in the specification and was removed, and the other
assertions of that test remain.

A first look at S2, with five replications at three thresholds, was not recorded
and is not a result. It raised a question for B7. By hand, an ideal signal at the
highest threshold alarms at the first degradation event of a machine, which is
10.8 hours on average for a regular machine and 3.2 for M3, and repairs it in 2.5
hours. That gives about 880 repairs per machine and an availability near 78
percent. The model agrees with this calculation. The perfect monitoring row of
the reference case has 669 repairs and 66.09 percent availability (p. 421), which
would need an average downtime of about 5 hours per repair, and its mean quality
of 0.79 is far below what the model gives at a high threshold. The paper
publishes only the setting with the highest quality and does not say which it is
or on which scale the threshold lies, so the difference may come from that, from
the classification of the repair time, or from the quality. It is not resolved,
and B7 has to examine it with a recorded run before S2 is interpreted.

**Limits.** The influence of A11 and A12 on S2 and S3 has not been examined. The
common random numbers hold for the degradation of a machine only up to its first
preventive repair (ADR-0014). The signal is a pair of error rates and not a
measurement, so the model cannot say how a real sensor would produce them.

**Next.** B7, experiments and results.

## 2026-10-06 (seventh entry)

**Worked on.** Backlog item B7, experiments and results. The scenarios S2 to S4
are defined in code: S2 varies the alarm threshold over the seven health values
with an ideal signal, S3 a grid of four detection and four false alarm
probabilities at the threshold of the best S2 setting, and S4 the buffer
capacity over 0, 1, 2, 5, 10, 15, and 20 parts for the run to failure and for
that setting. All use the root seed 2026, so that their replications pair. The
analysis gained the paired differences with confidence intervals, which common
random numbers make narrower than two independent intervals, and the rule for
the best scenario. The new `plots` module writes three figures as PDF and as PNG
at 300 dots per inch, black on white with the 95 percent interval as error
bars. The command `uv run python -m takt all` produces every table and figure in
`docs/figures/`, including the validation of S1 and a check of the initial
transient. Replications can run in separate processes, and the tables of a
serial run and of a run with 18 workers are identical byte for byte. The suite
has 144 tests and passes together with the static checks.

**Decisions.** The best setting is the threshold with the highest output, the
warm-up of S4 is 516 hours, and the replications run in parallel (ADR-0015). The
published perfect monitoring system is compared with every threshold of S2, and
the one with the highest quality in the model is marked.

**Results.** All values are from the working tree on top of commit 034178f, root
seed 2026, 50 replications, warm-up of 252 hours for S1 to S3 and 516 hours for
S4, 95 percent confidence level. Differences are paired by replication.

| Setting | Parts produced | Difference from S1 | Quality | Availability | Repairs per machine | Lead time (h) |
| --- | --- | --- | --- | --- | --- | --- |
| S1, run to failure | 4,746.8 ± 15.3 | | 0.603 | 76.70 % | 115.3 | 52.0 |
| S2, threshold 0.125 | 7,494.5 ± 24.4 | +2,747.7 ± 24.9 | 0.630 | 90.53 % | 159.1 | 34.9 |
| S2, threshold 0.5 | 8,240.6 ± 8.1 | +3,493.8 ± 14.3 | 0.809 | 92.41 % | 286.4 | 31.7 |
| S2, threshold 0.875 | 5,996.2 ± 16.0 | +1,249.4 ± 20.1 | 0.988 | 78.26 % | 876.7 | 42.7 |

The output of S2 is above that of S1 at every threshold, and every difference
is clear. It is highest at 0.5, the best setting, and lowest at 0.875, where the
quality is highest. It is not monotone: it is 7,901 at 0.25, 7,697 at 0.375, and
8,241 at 0.5. A change of the repair class at a health of 0.5 is consistent with
the step, because a repair from 0.5 upwards takes 2.5 hours and below it 5
hours, but this was not tested. The work in progress is 20.5 to 21.1 parts at
every threshold against 21.9 under S1, and the lead time falls from 52.0 hours
to between 31.7 and 42.7 hours.

For S3 at a threshold of 0.5, the ideal signal gives the 8,240.6 parts of S2.
A false alarm probability of 0.05 per reading with perfect detection costs 531
parts, about 2,620 false alarms per run, and raises the quality from 0.809 to
0.875 and the repairs per machine from 286 to 577. A detection probability of 0.5
without false alarms costs 211 parts. The worst corner, detection 0.5 and false
alarms 0.05, gives 7,582 ± 11 parts, which is 2,835 ± 19 above S1. Every cell of
the grid is clearly above S1.

For S4, the output under the run to failure rises from 2,098.6 parts at a
capacity of 0 to 5,336.7 at 20. Under the best setting it is 6,645.9 at 0, 7,601.7
at 1, 8,070.2 at 2, and 8,240.6 at every capacity from 5 to 20, identical in
every replication. This is consistent with an output that M3 alone limits once
the buffers absorb the other machines, which was not tested. The advantage of the
best setting is 4,547 ± 30 parts at a capacity of 0, 5,168 ± 22 at 2, and 2,904 ±
14 at 20. The work in progress grows in proportion to the capacity, and the lead
time from 14.3 hours at 0 to 82.4 hours at 20 under the run to failure and from
7.5 to 56.1 hours under the best setting.

**Surprise.** The reference case reports that the perfect monitoring system
lowers the output from 4,730 to 3,971 parts and the availability from 76.7 to
66.1 percent (p. 421), and the model gives a higher output and availability at
every threshold. At the threshold with the highest quality, 0.875, it gives 5,996
parts, 78.26 percent, 876.7 repairs, and a quality of 0.988, against 3,971.2
parts, 66.09 percent, 669 repairs, and a quality of 0.79 published. No threshold
of the sweep reproduces the published row, which `s2-vs-published.csv` shows for
all seven. The model validates for the run to failure (B5), so the difference
lies in the condition-based policy or in the reading of it. The causes that come
to mind are the scale of the threshold, the classification of the repair time by
health, the definition of the quality, and a delay between the alarm and the
repair, but none was tested, and the paper does not give the information to
decide. The results of S2 to S4 are therefore results of this model and are not
validated against the paper. This limits what the report can claim about the
trade-off between quality and output, and it is part of the critical
reflection.

**Check of the warm-up.** The truncation points of S1, of the lowest and highest
threshold of S2, and of the worst signal of S3 are at most 252 hours. The run to
failure needs 276 hours at a capacity of 0 and 348 and 516 hours at a capacity of
20 for the output and the work in progress. A first run of the command with the
warm-up of 252 hours for S4 showed this in its own table, and the warm-up of S4
was raised to 516 hours and the whole set run again.

**Runtime.** The complete set took 6 min 43 s with one worker and 40 s with 18
workers on the machine of the author, so NFR6 is met on a single core. The first
version of the command started a pool of processes also for a single task, which
made the test suite several seconds slower, and the number of workers is now
limited to the number of tasks.

**Problems.** The first version of the figure module chose its file backend after
an import and silenced the resulting finding with a comment for the linter. This
is not allowed without a decision record, so the order of the statements was
changed instead, and the finding does not occur. The error bars of most points
are smaller than the markers, because the intervals of 50 replications are
narrow, which is a property of the results and not a defect of the figures.

**Limits.** The conditions of S2 to S4 depend on A11 and A12, and on the signal as
a pair of error rates. The false alarm probabilities are per reading and machine,
and their scale is a choice. The capacities between those whose transient was
checked are assumed to lie between them. A capacity of zero gives a work in
progress of zero by the definition of the reference case (ADR-0012).

**Next.** B8, structure diagrams and final review.

## 2026-10-06 (eighth entry)

**Worked on.** Backlog item B8, structure diagrams and final review. The
component diagram shows the seven modules of the package, the arrows of their
imports, and the five libraries, and the sequence diagram shows one replication
from the seeds to the indicators. Both were drawn from the source files and
render without errors. A new test, `tests/test_diagrams.py`, makes the match
checkable: the arrows of the component diagram have to equal the imports found in
the source files by their syntax tree, and every function and class that the
sequence diagram names has to exist in the code. The README now describes the
commands, the layout of the package, and the reproduction of the figures. Every
requirement has its final status: FR1 to FR13 and NFR1 to NFR7 are done, and FR14
and FR15 stay deferred for the reason given in `requirements.md`. NFR1 and NFR4,
which were still partly met, are done.

**Fresh clone.** The complete set of experiments was repeated from a fresh clone
of commit 1fda651 with the changes of this item applied, in a new virtual
environment created with `uv sync --locked`, and without the folder of raw
results. The suite of 148 tests and the static checks passed there, and
`uv run python -m takt all` took 41 seconds with 18 workers. All 18 files in
`docs/figures/` are identical to the ones in the working tree, byte for byte,
with the root seed 2026, 50 replications, and the warm-up periods of ADR-0011 and
ADR-0015.

**Problems.** The committed PDFs carry the date of their creation, for instance
`D:20261006202927`, so that a repeated run would have written different bytes for
the same data. This was seen in the committed files and not in a failed
comparison. The date is now left out of the PDF, the three PDFs of the figures
were written again, and a test saves the same figure twice, a second apart, and
compares the bytes. The CSV files and the PNG files did not change. The remaining
check of the claim that the clone reproduces the figures therefore had to use the
changes of this item on top of the last commit, which is stated above. A second
point is a limit of the check: it was made on one machine, with the same
operating system and the same fonts, and the figures use Arial only where it is
available, otherwise a substitute font, so that a machine with other fonts may
draw the figures differently while the tables stay the same.

**Size of the implementation.** The package has 8 files with 2,410 lines, of which
1,971 are not blank and not comments, with `model.py` at 610, `experiment.py` at
393, `analysis.py` at 346, `cli.py` at 255, `config.py` at 206, and `plots.py` at
152. The 13 files of tests have 1,872 lines, of which 1,279 count the same way,
and hold 148 tests. The repository has 6 diagrams, 15 decision records, and 11
commits before this item. The count of code lines includes the docstrings.

**Limits of the project.** Three are carried into the report. The condition-based
policy has no published counterpart that the model reproduces, so S2 to S4 are
results of the model and not validated, see the journal entry of B7. The model
covers one configuration and two policies, and the periodic inspection and the
parallel configurations of the reference case are deferred. The assumptions A3 to
A5, A11, and A12 were not varied, and the signal is a pair of error rates and not
a measurement.

**Next.** The report is written from `docs/` and from the files in
`docs/figures/`, which are complete.
