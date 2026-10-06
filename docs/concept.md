# Concept

Status: fixed in backlog item B1. Changes after this point are recorded in
`decision-log.md`.

## Initial situation

Condition monitoring is one of the standard promises of a smart factory.
Sensors record the condition of a machine, a degradation is detected before
the machine fails, and the long unplanned repair is replaced by a short
planned intervention. Whether this pays off for a production line is less
obvious than it sounds. Every intervention stops the machine, so a monitoring
system that reacts early protects the product quality and avoids failures, but
it also takes the machine out of production more often.

A published simulation study illustrates the conflict. Dadfarnia et al. (2023)
simulate a line of six milling machines under several maintenance policies. In
their serial configuration, a monitoring system with perfect knowledge of
every machine raises the mean product quality from 0.60 to 0.79 compared with
running the machines to failure, but the number of parts produced falls from
4,730 to 3,971 and the machine availability from 76.7 percent to 66.1 percent
(p. 421). The authors report these values for the alarm setting that maximises
quality and do not examine other settings or signal qualities for this policy.

## Reference case

The reference case is the serial configuration C1 of Dadfarnia et al. (2023,
p. 420). The authors describe it as a fictional configuration of six 3-axis
milling machines that produce a single type of part. It is used here as a case
study based on the literature, because it is documented with a complete set of
parameters and with published results that an independent model can be
compared against.

Raw parts enter at a source, pass the six machines M1 to M6 in a fixed order,
and leave at a sink. A buffer lies between two neighbouring machines, so the
line has the five buffers B1 to B5.

## Objective

The model reproduces the published case independently and then extends it. It
answers three questions.

1. Does an independent implementation of the documented model reproduce the
   published availability, repair count, output, and quality of the line under
   the run-to-failure policy.
2. How do output, lead time, and product quality change with the alarm
   threshold of the monitoring system, and is there a threshold at which
   condition-based maintenance improves the output of the line instead of
   reducing it.
3. How sensitive is the result to the quality of the sensor signal, expressed
   as missed alarms and false alarms, and to the capacity of the buffers.

The purpose of the model is decision support before an investment: it shows
under which settings a condition monitoring system is worth introducing on a
line of this kind, and which performance indicator pays for it.

## Conceptual model

### Entities

- A part moves from the source through machines and buffers to the sink and
  carries a quality indicator between 0 and 1.
- A machine processes one part at a time and has a health indicator.
- A buffer stores waiting parts up to its capacity.
- A maintainer repairs one machine at a time. Work orders wait in a queue in
  the order in which they were created.
- The monitoring system reads the health of every machine at a fixed interval
  and creates work orders.

### Machine health and degradation

The health indicator of a machine takes the nine values 1, 0.875, 0.75, and so
on down to 0. Every degradation event lowers it by 0.125, and the time between
two degradation events follows a Weibull distribution. At 0 the machine has
failed. Every completed repair restores the health to 1.

### Machine states

A machine that is able to work is processing a part, starved because no part
is available upstream, or blocked because the downstream buffer is full. A
failed machine waits for a maintainer and is then under corrective repair. A
machine with a pending work order keeps producing until the maintainer
arrives and is then under preventive repair. The states are shown in
`diagrams/machine-states.puml`.

### Events

Arrival of a part at the source, start and end of processing on a machine,
degradation of a machine, failure of a machine, sensing of the machine health,
creation of a work order, start and end of a repair, and the end of the run.

### Product quality

Every machine adds a share of quality to the part it processes. With six
machines the full share is one sixth, and the share actually added is one
sixth multiplied by the health of the machine at that moment. A part that
passes six machines in perfect health leaves the line with a quality of 1.

## Parameters

Parameters taken from the reference case. Page numbers refer to Dadfarnia et
al. (2023).

| Parameter | Value | Unit | Page |
| --- | --- | --- | --- |
| Machines in series | 6 | | 420 |
| Buffers between machines | 5 | | 420, Fig. 4 |
| Cycle time per machine | 1 | hour | 420 |
| Buffer capacity | 10 | parts | 420 |
| Arrival rate at the source | 1 | part per hour | 420 |
| Initial health of every machine | 1 | | 417 |
| Health reduction per degradation event | 0.125 | | 417 |
| Time between degradation events, M1, M2, M4, M5, M6 | Weibull, shape 1.5, scale 12 | hours | 417, 420 |
| Time between degradation events, M3 | Weibull, shape 0.9, scale 3 | hours | 417, 420 |
| Repair time after a failure | 20 | hours | 418, 422 |
| Repair time at a health above 0 and up to 0.5 | 5 | hours | 419, 422 |
| Repair time at a health of 0.5 or more | 2.5 | hours | 419, 422 |
| Maintainers | 3 | | 420 |
| Sensing interval of the monitoring system | 1 | hour | 418, 422 |
| Quality share per machine | 1/6 | | 416 |
| Run length | 10,080 | hours | 420 |
| Replications | 50 | | 420 |

The cycle time follows from two statements on p. 420: the cycle times of all
machines on a path add up to 6 hours, and they are equal within a
configuration.

Variables of the extension. They are not taken from the reference case and
are the quantities that the scenarios S2 and S3 vary (ADR-0006, ADR-0014).

| Variable | Ideal value | Range | Unit | Basis |
| --- | --- | --- | --- | --- |
| Alarm threshold | not applicable | 0.125 to 0.875 in steps of 0.125 | health | scenario variable of S2, no source |
| Detection probability, a reading at or below the threshold raises an alarm | 1 | 0 to 1 | probability | scenario variable of S3, no source |
| False alarm probability, a reading above the threshold raises an alarm | 0 | 0 to 1 | probability | scenario variable of S3, no source |

Rules taken from the reference case:

- A machine that fails stops, accepts no further parts, and scraps the part it
  is processing (p. 417).
- A preventive repair pauses the machine when the maintainer arrives and
  scraps nothing (p. 419).
- The monitoring system creates a work order when it reads a health at or
  below the alarm threshold (p. 418).
- A machine that fails while its work order is waiting receives the
  corrective repair (p. 418).
- Parts that are still inside the line at the end of the run are not counted
  as produced (p. 416).

## Assumptions

Points that the reference case leaves open or states ambiguously. Each one is
a decision of this project and is examined again in the validation, B5.

| ID | Assumption | Reason |
| --- | --- | --- |
| A1 | The scale parameter of the Weibull distribution is in hours. | The paper gives no unit. Every other duration in it is in hours, and the analytic check below reproduces the published availability with this reading. |
| A2 | Degradation proceeds in clock time whenever the machine is not failed or under repair, also while it is starved or blocked. | The paper calls the degradation tied to the use of the machine (p. 415), but it reports nearly the same availability for all five configurations (p. 421), which is only possible if degradation does not depend on how much a machine produces. |
| A3 | The cycle time is constant. | The paper allows constant or random cycle times (p. 415) and names no distribution for the case study. |
| A4 | Repair times are constant. | The paper adds a variance term to the repair time (p. 418) without giving its size. |
| A5 | The two noise terms of the quality equation are zero. | The paper describes them as small and gives no values (p. 416). |
| A6 | A health of exactly 0.5 is repaired in 2.5 hours. | The paper assigns 0.5 to both repair classes (p. 419). |
| A7 | The source offers one part per hour and waits when the first machine cannot accept it. No part is lost in front of the line. | The paper gives the rate only (p. 420). |
| A8 | Work orders are served in the order of their creation, and a failed machine has no priority over a planned repair. | The paper describes a queue without a priority rule (p. 415). |
| A9 | A failure scraps only a part that is in process. A part that has finished processing and waits for buffer space is handed over, and a machine that fails while starved has taken no part. | The paper scraps the part in process (p. 417) and does not say what happens to a finished part held by a blocked machine. |
| A10 | A machine adds its share of quality when it completes the cycle, with the health at that moment, and the quality of a part is the mean of these health values over all machines. | The paper multiplies the share by the health without saying at which point of the cycle it is read (p. 416). The completion is the moment at which the share is added, and a degradation event inside the cycle is part of the condition under which the part was finished. |
| A11 | A preventive repair pauses the part in process, which keeps the work already done and is finished after the repair with the remaining cycle time. | The paper pauses the machine and scraps nothing (p. 419) and does not say how the cycle is resumed. |
| A12 | A machine has at most one open work order. An alarm for a machine with an open order is ignored, and a machine that fails while its order waits keeps the order and its place in the queue, which then calls for the corrective repair. | The paper lets a machine that fails while its work order waits receive the corrective repair (p. 418) and does not say whether a second order is created. |

## Analytic expectation

Under A1 and A2, and as long as a maintainer is always available, the
availability of a machine under the run-to-failure policy can be derived
without simulation. The mean time between two degradation events is the scale
multiplied by the gamma function of one plus the reciprocal of the shape,
which gives 10.83 hours for the five regular machines and 3.16 hours for M3.
Eight events lead to a failure, so the mean time to failure is 86.66 hours and
25.25 hours. With a repair of 20 hours this yields the following values.

| Quantity | Regular machine | M3 | Mean of six | Published, C1 (p. 421) |
| --- | --- | --- | --- | --- |
| Availability | 81.2 percent | 55.8 percent | 77.0 percent | 76.70 percent |
| Repairs in 10,080 hours | 94.5 | 222.8 | 115.9 | 115.12 |

The standard deviation across the six machines is 9.48 percentage points for
the availability and 47.8 for the repair count, against published values of
9.484 and 47.427. The agreement supports A1 and A2 and gives B5 exact targets
for the verification of the degradation and repair logic.

## Scenarios

| Scenario | Maintenance | Purpose |
| --- | --- | --- |
| S0 | none, machines never degrade | verification against exact values |
| S1 | run-to-failure | validation against the published results and baseline |
| S2 | condition-based with an ideal signal, alarm threshold varied from 0.125 to 0.875 | question 2 |
| S3 | condition-based with an imperfect signal: missed alarms and false alarms | question 3 |
| S4 | S1 and the best setting of S2 with buffer capacities from 0 to 20 | question 3 |

## Performance indicators

- Parts produced per run and throughput in parts per hour.
- Lead time of a part from entering the first machine to reaching the sink.
- Work in progress as the time average of the parts waiting in buffers, which
  is the definition of the reference case (p. 419).
- Machine availability as the share of time in which a machine is neither
  failed nor under repair (p. 419).
- Number of completed repairs per machine, corrective and preventive (p. 419).
- Mean product quality of the produced parts (p. 419).
- Number of scrapped parts.
- Share of time per machine spent processing, starved, blocked, waiting for a
  maintainer, and under repair.

## System boundary

Inside the model: the six machines, the five buffers, the source and the sink,
the degradation and repair of the machines, the maintainers, the monitoring
system, and the quality indicator of the parts.

Outside the model: the four other configurations of the reference case, its
periodic inspection policy, and its two monitoring systems that infer the
machine health from the quality of finished parts. The supply chain, demand,
rework, shift calendars, and the cost of sensors and repairs are outside as
well. The imperfect signal of S3 stands in for the inferring systems in a
simpler form: it does not model an algorithm, only the error rates that such
an algorithm produces.

## Method

The model is a discrete-event simulation. Every scenario is run in several
independent replications, and the results are reported as means with
confidence intervals. The scenarios share the same random number streams, so
that a difference between two scenarios stems from the policy and not from
chance. S1 is run with the run length and the number of replications of the
reference case, so that the comparison with the published values is like for
like.

## Source

Dadfarnia, M., Drozdov, S., Sharp, M. E., & Herrmann, J. W. (2023). A
simulation-based approach to assess condition monitoring-enabled maintenance
in manufacturing. 2023 7th International Conference on System Reliability and
Safety (ICSRS), 413-422. https://doi.org/10.1109/ICSRS59833.2023.10381326
