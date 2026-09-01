# Design references — index

This file was a single 21KB document. It has been **split**, so each consumer
reads only what it needs. Nothing here but pointers.

| Read | For |
|---|---|
| [`design-principles.md`](design-principles.md) | DI-1…DI-12, **each classified** ① fundamental / ② current decision / ③ implementation property — plus §8, the claims that were retracted. Everyone reads this |
| [`state-ownership.md`](state-ownership.md) | Vocabulary, what produces what, the state families and their authorities, the four kinds of transition |
| [`orchestration-model.md`](orchestration-model.md) | The two orchestrators (and why that split is an open question, not a decision), the placement test for agent / node / function, information-flow constraints, cost |
| [`design-history.md`](design-history.md) | Which document argues which domain, and the eleven responsibilities that have already moved — with what each earlier arrangement cost |

Typical loads: **learning-system-designer** → principles + state-ownership +
history. **orchestration-designer** → principles + orchestration-model + history.
**Reviewers** → principles + the one model file for their subsystem.
**investigate-behaviour** → principles §DI-1/DI-5 + state-ownership §3.
