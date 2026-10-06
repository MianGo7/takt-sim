# Diagrams

The diagrams of the report, kept as PlantUML sources so that they are
versioned together with the code they describe and every change to a model is
visible in the history. Each diagram is listed with the backlog item that
produces it and its status. The conceptual diagrams are drawn before the model
is implemented and revised afterwards; the structure diagrams are drawn from
the implemented code.

| File | Diagram | Item | Status |
| --- | --- | --- | --- |
| `line-process-flow.puml` | Layout of the line with source, machines, buffers, sink, maintainers, and monitoring system | B1 | done |
| `machine-states.puml` | State diagram of a machine | B1 | done |
| `maintenance-activity.puml` | Activity diagram of the creation and service of a work order under the two maintenance policies | B6 | done |
| `package-components.puml` | Component diagram of the simulation package, with the imports between modules and libraries | B8 | done |
| `replication-sequence.puml` | Sequence of one replication from the seeds to the indicators | B8 | done |

## Conventions

- Every diagram includes the shared style with `!include _style.puml` and
  opens with `@startuml` followed by its file name.
- Notation is UML 2.5.
- Names of classes, attributes, methods, and states match the code exactly.
- The diagrams are rendered with
  `plantuml -tsvg -o out docs/diagrams/<file>.puml`. The rendered files are
  generated output and are not versioned.
- The structure diagrams are checked by `tests/test_diagrams.py`: the arrows of
  the component diagram have to equal the imports of the source files, and every
  function and class named in the sequence diagram has to exist in the code.
