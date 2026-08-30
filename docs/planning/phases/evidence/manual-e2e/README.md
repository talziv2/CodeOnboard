# Manual E2E round — lesson-content review

**Status: WALK COMPLETE, 2026-08-18. The analysis is in [`SYNTHESIS.md`](SYNTHESIS.md) — read that first; this file is the evidence of record, ordered by the walk.** This is the manual validation round
[`learning-graph.md`](../../learning-graph.md) schedules for the end of the
phase, and the round M3b's thresholds are waiting on. It is a working record,
not yet a closed evidence document. **No production code has been changed on the
strength of anything below** — findings are collected across the whole journey
first, because content judgements calibrate across a journey and not one lesson
at a time.

Labelling follows `learning-graph.md`: **[FACT]** verified in this repository
with a file:line or a query, **[REC]** a recommendation, **[OPEN]** needs a
decision.

## Configuration

| | |
|---|---|
| session | `cff533a5ff4e409bbd78a293d0fd465c` |
| repository | `aimacode/aima-python` |
| goal | `use_library` — "Use the search algorithms from AIMA in my own project" |
| flags | `CODEONBOARD_CURRICULUM=1`, `CODEONBOARD_GAPS=1` (both from `.env`, verified live) |
| journey | 16 units, 5 areas |
| backend | uvicorn without `--reload` (a reload mid-`/session/start` kills the request) |

## Reviewer verdicts and what the artifact actually says

### Lesson 1 — "Map the Problem contract"

| | |
|---|---|
| node | `81b7b1723cae4b31a1442e4ac9a1ee3c` |
| kind / priority / area | `component` / `required` / `a1` |
| anchor | `search.py` `Problem` 15–62 (one anchor, resolves) |
| outcome | answered once, classified `understood`, `gap_kind: none`, 0 gaps |

**Reviewer verdict:** keep the lesson and its position; the `Problem` contract is
the right thing to establish before `Node`, BFS/UCS/A*. The comprehension
question (omit `actions()` vs omit `path_cost()`) tests the contract rather than
recall. Concern raised against the framing sentence "It defines five methods: two
that you must implement, two you may override, and one that has a working
default", and a request to check the expected answer describes real runtime
behaviour.

**The concern is correct, and the defect is upstream of the lesson.**

**F1 — [FACT] The planner's objective contradicts itself and names a method the
unit does not contain.** `lesson_brief["objective"]` opens *"Name the **four**
methods a Problem subclass must or may implement (actions, result, goal_test,
path_cost, **h**)"* — a stated count of four followed by an enumeration of five.
`h` is not a member of `Problem`. `Problem`
([search.py:15-62](../../../../../data/repos/aima-python/search.py)) defines
`__init__`, `actions`, `result`, `goal_test`, `path_cost`, `value`; `h` is
defined on `GraphProblem` at `search.py:1206` — a **different unit of the same
journey** (`0ba8f6d3…`, "Use GraphProblem for map-based search", area a2), whose
own objective correctly credits `h` to `GraphProblem`. So a downstream unit's
method leaked into this unit's objective. The prose count of four is the
defensible one; the parenthetical list is what is wrong.

**F2 — [FACT] Teaching inherited the broken contract and produced a partition
that matches neither the code nor its own reveal.** Under B1 Teaching is
instructed to build exactly the objective, so this is correct behaviour against a
faulty input, not a Teaching defect. Given "four" plus five names it wrote *"five
methods: two that you must implement, two you may override, and one that has a
working default"*. Measured against the source, `Problem` is **3 methods that
raise `NotImplementedError`** (`actions`, `result`, `value`) and **2 with working
defaults** (`goal_test` → equality/membership against `self.goal`; `path_cost` →
`c + 1`). There is no "two may override, one working default" grouping anywhere.
The lesson also **contradicts itself internally**: its own `reveal` describes
`actions`/`result` raising, `goal_test` defaulting, `path_cost` defaulting and
`h` raising — 2 mandatory / 2 defaulted / 1 raising, which is not the split its
`setup` announced two paragraphs earlier.

**F3 — [FACT] `value()` is never mentioned, and truncation is not the reason.**
`Problem.value` (`search.py:57-60`) raises `NotImplementedError` and is the third
genuinely-abstract method. The unit's anchor spans 15–62, so `value` **was inside
the source Teaching read**. Omitting it is defensible for a search-focused
`use_library` goal — hill-climbing is not on this journey — but then the count is
four, and the slot `h` currently occupies is the one `value` was dropped from.

**F4 — the reviewer's second concern is already satisfied by the artifact.**
`expected_answer` does describe real runtime behaviour in this repository, in the
specific terms asked for: omitting `actions()` "gets `NotImplementedError`";
omitting `path_cost()` "the default returns `c + 1`, so every action costs 1
regardless of your domain's true cost". No change needed. Recorded because a
round that only lists faults mis-describes the system.

**F5 — [FACT] the defect cost this learner nothing, measurably.** The submitted
answer addressed only `actions()` and `path_cost()`, said nothing about `h`, and
was classified `understood` / `gap_kind: none` with a rationale tracking the
objective's real payload (loud failure vs silent unit-cost). The Grader marked
the substance, not the enumeration. **So F1–F3 are a correctness defect in what
the learner is told, not yet a demonstrated harm to learning** — the bar
`gap-model.md` sets for reopening work.

**Checked and clean — recorded so they are not re-investigated:**

- **Not an encoding defect.** The em-dashes render as `?` in a cp1252 console but
  are stored as U+2014. Verified on the raw column.
- **"Crashes when a search algorithm calls it" is precise, not loose.** `Problem`
  is not an `abc.ABC` and uses no `@abstractmethod`, so a subclass missing
  `actions()` **instantiates fine** and fails only at expansion. The reveal says
  exactly this. (The `setup`'s word "abstract" is the class docstring's own, not
  Python's.)
- **`visited: 0` on a graded node is expected** — `/advance` sets it and the
  learner has not advanced.

**[REC] Where a fix would go, if the pattern repeats.** F1 is a planner-side
objective defect, so the candidate fix is in `backend/agents/mentor/curriculum.py`
— not in Teaching, which behaved correctly. **Deferred until the journey shows
whether this is a one-off or systematic**: a single leaked method name does not
justify touching the planner. The specific thing to watch on later units is
whether other objectives name symbols that are not inside their own anchors —
that is mechanically checkable against `anchors.resolve` and would be a test, not
a prompt change.

**[OPEN] Should an objective's named symbols be required to resolve within the
unit's own anchors?** It is checkable deterministically and would have caught F1
at plan time. It would also forbid legitimate forward references ("…so that a
`GraphProblem` can later supply `h`"). Not decided; revisit at the end of the
round with a count of how often it would fire.

#### Lesson 1, second pass — the post-answer feedback (`reveal` / `takeaway`)

Reviewed separately from the question, because it is a separate artifact with a
separate failure mode: the learner reads it **after** answering, as authoritative
correction.

**Reviewer verdict:** the answer was correct for the question asked; the
generated explanation introduces two overgeneralizations — `h()` is described as
raising `NotImplementedError` and then grouped with methods that "silently change
behaviour", and omitting `path_cost()` is called getting "the wrong answer
silently" when `c + 1` is simply correct for unit-cost domains.

**Both are confirmed. The `h()` one is worse than reported.**

**F6 — [FACT] `Problem` has no `h` at all, and the real failure is eager and
louder than the lesson claims.** The reveal states *"`h()` (heuristic) raises
`NotImplementedError`"*. There is no `h` on `Problem`
([search.py:15-62](../../../../../data/repos/aima-python/search.py)) to raise
anything. `astar_search` ([search.py:415-420](../../../../../data/repos/aima-python/search.py))
begins `h = memoize(h or problem.h, 'h')`, so a subclass without `h`, called
without the `h=` argument, raises **`AttributeError: '…' object has no attribute
'h'` on the first line of `astar_search`, before the search starts** — not
`NotImplementedError`, and not at the point the heuristic is needed. The
reviewer's correction (that it fails when A* wants a heuristic) is the right
direction and the truth is earlier and more abrupt.

**F7 — [FACT] the `takeaway` contradicts the `reveal` it follows.** `takeaway`:
*"Optional methods like `goal_test()`, `path_cost()`, and `h()` have defaults or
are algorithm-specific; omitting them **silently changes behaviour rather than
failing**."* The `reveal`, two paragraphs earlier, says `h()` raises. Both cannot
hold, and per F6 neither is what the code does. This is the **third** internal
contradiction inside this one lesson (see F2).

**F8 — [FACT] "wrong answer silently" is an overgeneralization, and the lesson's
own graded field is the careful version.** `reveal`: *"You get the wrong answer
silently, not an error."* The default `c + 1` is **correct** for a unit-cost
domain; the failure requires non-uniform costs *and* a missing override, and what
degrades is optimality under the intended cost model. The unit's own
`expected_answer` states exactly that — *"may not be optimal by your actual
costs"* — so the disciplined claim already exists in the same payload.

**F9 — the structural finding, and the reason F6–F8 all landed in the same
place. [FACT]** In this lesson, every careful claim is in a field the system
consumes downstream (`objective`, `expected_answer` — the B1 contract the Grader
marks against) and every overgeneralization is in free prose no consumer ever
reads (`setup`, `reveal`, `takeaway`). **The `reveal` is the only substantial
learner-facing text with no downstream reader**, so nothing — not grounding, not
the Grader, not `anchors.resolve` — can catch an error in it. It is also the text
the learner meets with their guard down, immediately after being told they were
right. F5 recorded that the objective defect cost this learner nothing because
the Grader marked substance; the reveal has no such backstop.

**[REC] Treat this as a learning-engine quality item, not a gap-model one.** The
reviewer's framing is the right one: post-answer teaching text needs the same
grounding discipline as the question, because a correct answer followed by a
confident wrong explanation *installs* a misconception the system will never
detect — the learner has already passed, so no gap can open. This is adjacent to
CLAUDE.md's "no source, no lesson" rule but not covered by it: that rule
guarantees the model **had** the source, not that its prose agrees with it.
Candidate responses, none taken yet:

- a `reveal`-scoped check that symbols named in the prose resolve within the
  unit's anchors (shares machinery with the [OPEN] question above, and would have
  caught `h` in both places);
- instructing Teaching to state failure modes in the terms the source shows
  (exception type and where it is raised), which `expected_answer` already
  manages and the prose does not.

**Deferred to the end of the round.** One lesson cannot show whether prose drift
is systematic; the count across 16 units can. The specific thing to tally on
later units: **does the free prose (`setup`/`reveal`/`takeaway`) contradict the
graded fields (`objective`/`expected_answer`) of the same unit?** If that holds
up as a pattern it is a strong, cheap finding — one comparison per unit, no
judgement call.

### Lesson 2 — "Write a minimal Problem subclass"

| | |
|---|---|
| node | `f5cc8df5edf748df9c791bc159f93546` — **stop 3** of 16 in `path_order()`, not stop 2 |
| kind / priority / area | `extension_point` / `required` / `a1` |
| anchors | `search.py` `Problem` 15–62 **and** `GraphProblem` 1179–1215 |
| outcome | answered once, classified `understood`, `gap_kind: none`, 0 gaps |

**Reviewer verdict:** good objective, natural progression from lesson 1
(understand the interface → use the interface). Three issues raised: the lesson
opens *"Now that you understand Graph's structure and how to query it…"* when
`Graph` has not been taught; the defaults question should test *when* the
inherited defaults are semantically appropriate rather than that they exist; and
calling `value()` an "optional optimization method" is confusing.

**F10 — [FACT] The plan order is correct. The learner skipped the stop, and the
lesson asserted knowledge from it anyway.** `path_order()` is `1. Map the Problem
contract → 2. Understand the Graph data structure → 3. Write a minimal Problem
subclass`, carried by a real `sequence` edge. So the fix the review proposes —
"the relevant Graph lesson should come first" — is already what the planner
produced. What happened instead:

- stop 2 has **no cached lesson, 0 attempts, `not_started`** — it was never taught;
- **every `visited` flag in the graph is 0**, including stop 1, which *was* taught and answered;
- `/advance` marks the current node visited unconditionally ([api.py:607](../../../../../backend/api.py)), so **`/advance` was never called in this session**;
- `journey_events` is empty, so no mutation moved the pointer;
- the only endpoint that moves `current_node_id` without marking visited is `/jump` ([api.py:1061-1068](../../../../../backend/api.py)) — rail navigation.

Frontend wiring is correct and not the cause: Continue calls `advance`
([LessonPanel.tsx:189](../../../../../frontend/components/LessonPanel.tsx)), a rail
click calls `jump` ([page.tsx:151](../../../../../frontend/app/session/[id]/page.tsx)).
So the learner reached stop 3 from the rail, and **`why_now` claimed a transfer
that never occurred.** `_previous_unit()` takes the predecessor from
`path_order()` (LQ4) — whose recorded justification is that it "stays correct
after a mid-session mutation". That reasoning covers mutation; it does not cover
a stop the learner did not take. The predecessor's `understanding_state` /
`visited` is available at that point and is not consulted.

**F11 — [FACT] Stop 3 and stop 4 share an identical anchor, so the unmet
prerequisite is real even for a learner who never jumps.** This unit's second
anchor is `GraphProblem` 1179–1215, which is **the entire anchor of stop 4**
("Use GraphProblem for map-based search"). Walking the path in order, the learner
meets `GraphProblem` as a teaching device one stop before it is the subject. The
`setup` leans on it heavily — "queries neighbors via `graph.get()`, and computes
edge costs from the Graph's adjacency structure" — while the *objective* only
asks for a toy-state-space subclass and never mentions `GraphProblem`. So the
second anchor serves the prose, not the contract. **Mechanically checkable:** does
a unit's anchor set contain another unit's whole anchor set, and does that unit
come later?

**F12 — [FACT] The two lessons give the same learner contradictory accounts of
the same class.** Both are anchored on `Problem` 15–62.

| | lesson 1 `setup` | lesson 2 `setup` |
|---|---|---|
| count | "five methods" | "five methods" |
| members | actions, result, goal_test, path_cost, **h** | actions, result, goal_test, path_cost, **value** |
| split | 2 must / 2 may override / 1 working default | 4 must-or-may / 1 "optional optimization method" |

Lesson 2's membership is **correct** (`h` is not on `Problem`; `value` is) and its
count is right. Lesson 1's is wrong (F1). Nothing reconciles them, and the learner
saw both within four minutes. A cross-unit consistency check over units sharing an
anchor would catch this; none exists.

**F13 — the "optional optimization method" wording is misleading, as reported.**
`Problem.value` ([search.py:57-60](../../../../../data/repos/aima-python/search.py))
raises `NotImplementedError` — it has no default, so "optional" in the sense the
sentence implies (like `goal_test`/`path_cost`) is wrong. It belongs to
*optimization problems* — `hill_climbing` (search.py:635) and the genetic
algorithms — not to an optimisation of the search contract. Grouping it with the
defaulted methods repeats lesson 1's category error with a different member.

**F14 — the defaults framing is already what the review asks for, and this
contradicts F9.** The semantic condition is stated in all three of the graded and
ungraded fields: the objective ("*when* uniform cost and single-goal semantics are
acceptable"), the `reveal` ("correct for uniform-cost problems where every move
costs the same; if moves had different costs, you'd override it"), and
`expected_answer` ("inherit `path_cost` because all moves cost 1. Override
`path_cost` only if moves have different costs"). It also worked: the submitted
answer volunteered "**if every slide has cost 1**" and the Grader's rationale
credited exactly that reasoning.

**So F9's pattern does not hold as stated.** Lesson 1 had careful graded fields
and drifting prose; lesson 2 has careful prose. One case each way — F9 is
downgraded from a finding to a hypothesis, and the per-unit tally it proposed is
now the thing that decides it, not a foregone conclusion.

**[REC] Two checks worth more than the individual fixes**, both deterministic and
neither requiring a model:

1. **`why_now` must not assert transfer from a unit the learner has not
   completed.** The predecessor's state is already loaded where `_previous_unit()`
   runs; the sentence can degrade to a plain statement of purpose. Cheapest fix in
   the round so far, and it repairs a false claim rather than a vague one.
2. **Flag a unit whose anchors contain a later unit's whole anchor set** (F11),
   and **compare units sharing an anchor for contradictory claims** (F12).

Still deferred to the end of the round — but note F10 and F12 are defects a
learner walking the path normally would still hit, so they do not depend on the
jump.

#### Lesson 2, second pass — the post-answer feedback

**Reviewer verdict:** the `understood` verdict is justified; the states-not-Nodes
distinction is a valuable thing to establish before `Node` and `expand()`; the
`path_cost` explanation is precise. One issue: the takeaway's *"Default
`goal_test` and `path_cost` suffice for uniform-cost, **single-goal** problems"* is
unnecessarily restrictive, because the default `goal_test` also handles a list of
goals — and the general principle should be whether the default semantics match
the domain.

**F15 — [FACT] "single-goal" is wrong, and the correct statement is sharper than
the proposed rewrite.** `Problem.goal_test`
([search.py:40-48](../../../../../data/repos/aima-python/search.py)) branches:

```python
if isinstance(self.goal, list):
    return is_in(state, self.goal)      # utils.is_in — identity
else:
    return state == self.goal           # equality
```

`is_in` is `any(x is elt for x in seq)`, documented in
[utils.py:76-78](../../../../../data/repos/aima-python/utils.py) as *"compares
with 'is', not '=='"*. So the two branches are **asymmetric**: a single goal
matches by **equality**, a list of goals matches by **identity**. A sliding-puzzle
state rebuilt each expansion will never satisfy the list branch no matter how
many equal boards it contains — while small ints and interned strings match by
accident, so it works in a toy example and fails on real states.

This makes the reviewer's principle exactly right and their proposed phrasing
still slightly too generous: "matches its equality/**membership** behavior" reads
as equality-based membership, which is the one thing the list branch is not. The
defensible statement is that the default suffices when a single goal compares
correctly under `==`, **or** when a list of goals holds the identical state
object.

**[REC] this looks like a missing `risk` unit, not just a wording fix.** The
journey already carries two units of exactly this shape — stop 15 teaches
`locations` missing → `h` returns `inf`, and `graph.get` returning `None` → `inf`
cost — and stop 12 teaches value-vs-identity for the explored set. The `is_in`
identity trap is the same failure class on the same class this journey opens
with, and no unit mentions it. Recorded as an observation about planner coverage;
**not acted on** — designing the curriculum is not what this round is for.

**F16 — [FACT] third contradiction between lessons 1 and 2 on the same class, and
F12 is now a pattern rather than an incident.** On `goal_test` specifically:

| | account of the list branch |
|---|---|
| lesson 1 `reveal` | acknowledged — "compares `state == self.goal` (or checks membership if `self.goal` is a list)" |
| lesson 2 `takeaway` | denied — "single-goal problems" |

Neither is right (F15), and they are wrong in opposite directions. With F12 (the
method *set*) and F16 (one method's *semantics*), two independent contradictions
now sit between two units sharing the anchor `Problem` 15–62. **The cross-unit
consistency check proposed in F12 is currently the highest-value candidate in
this round** — it is deterministic, needs no model, and would have caught three of
the defects recorded so far (F1/F12, F16).

**Confirmed good, and verified rather than assumed:** the states-not-Nodes
distinction is carried in both `reveal` and `expected_answer` ("must return the
*new state* … not a Node"), it is correct against `Node.expand`/`child_node`, and
it is genuinely load-bearing for stop 8 ("Extract information from a returned
Node") and stop 9 (the A* trace). The `path_cost` treatment is accurate as
reported — see F14.

### Walk defect — a forward `jump` orphans the stops it skips, permanently

**Reported from the session:** advancing from lesson 2 landed on the area
introduction for *Graphs and maps as input data* (a2), but the lesson queued
behind it was that area's **second** unit, not its first.

**Reproduced in stored state, and the report is accurate.** Documented only —
no fix attempted.

**F17 — [FACT] `next_in_path` resumes the `sequence` chain from wherever the
learner currently is, and nothing ever returns to a stop that was jumped past.**

Walk state after the advance:

| stop | area | visited | state | cached lesson |
|---|---|---|---|---|
| 1 Map the Problem contract | a1 | **0** | understood | Y |
| 2 Understand the Graph data structure | a2 | **0** | not_started | Y (rendered later, from the rail) |
| 3 Write a minimal Problem subclass | a1 | 1 | understood | Y |
| 4 Use GraphProblem for map-based search | a2 | 0 | not_started | Y (rendered by the advance) |

`next_in_path(stop 3)` returns **stop 4**, which is correct against the graph —
there is a real `sequence` edge `Write a minimal Problem subclass → Use
GraphProblem for map-based search`. The chain is a linear order and the walk
re-enters it at the current node, so the jump over stop 2 (F10) removed it from
the journey for good: **only a second rail click can ever reach it**, which is
what happened here.

**The area introduction itself is intended behaviour, not part of the defect.**
[page.tsx:113-119](../../../../../frontend/app/session/[id]/page.tsx) opens the
section overview when the current node enters a not-yet-introduced area whose
`settled` count is 0, and the comment at line 41 is explicit that it is a layer
over the lesson column rather than a destination. Entering a2 at stop 4 satisfies
that condition exactly. What makes it read as broken is the pairing: the header
introduces the area while the lesson behind it is that area's second unit, with
the first still untaken and no indication of it.

**F18 — [FACT] `visited` records "was advanced through", never "was studied", and
this is already visible in stored state.** Only `/advance` calls `mark_visited`
([api.py:607](../../../../../backend/api.py)); `/jump` does not
([api.py:1061-1068](../../../../../backend/api.py)). So stop 1 — taught, answered
and `understood` — is `visited=0` and will stay that way. `resume_point()` returns
the first unvisited non-optional node ([graph.py:634](../../../../../backend/learning/graph.py)),
which for this session is **stop 1**: a returning learner is sent back to a lesson
they already completed. Confirmed by calling it — it returns "Map the Problem
contract", not stop 2.

**Checked and clean — the progress numbers do *not* inherit this.** The header's
"2 of 15 stops taken" is right. `journey_progress` counts `progress.is_settled`
([progress.py:173-180](../../../../../backend/learning/progress.py)), the weaker
coverage predicate, not `visited`; the strict settling predicate lives separately
in [graph.py:163-177](../../../../../backend/learning/graph.py) and also does not
read `visited`. Recorded so that a fix to F18 is not mistaken for a fix to a
progress bug that does not exist.

**[REC] Not obviously one defect, and the shape of the fix depends on a product
call that has not been made.** The candidates are different in kind: make the
walk return to unfinished earlier stops; warn at the moment of a forward jump;
say on the area introduction that an earlier stop in it is untaken; or treat
"studied from the rail" as visiting. **[OPEN] Is a forward rail jump an
instruction to skip the intervening stops, or a detour the walk should later
undo?** `optional` already has an answer for a related question (stepped over,
kept in the graph), and F17/F18 are the same question for stops the learner
skipped by hand. Deferred with the rest of the round.

### Lesson 3 — "Understand the Graph data structure" (stop 2, reached from the rail)

| | |
|---|---|
| node | `a4fc6262445b4ba7bcb0a588b1db8df0` |
| kind / priority / area | `component` / `required` / `a2` |
| anchor | `search.py` `Graph` **1006–1058** (single anchor) |
| outcome | answered once → **`partial` / `wrong_model`**, one gap opened (`foundational=True`), `reteach` fired |

**Reviewer verdict:** relevant lesson, but it should come before lesson 2; the
`get('A','B')` question is good; the `locations`/heuristic half depends on
`GraphProblem.h()` and so tests more than the stated objective — either `h`
should be an explicit anchor or that question belongs in a later A* lesson.

**Every part of this is right, and the consequence is the most serious finding of
the round.**

**F19 — [FACT] The rail displays a different order than the walk follows, and it
is what induced the jump in F10.** `buildRoute`
([graph-layout.ts:72](../../../../../frontend/lib/graph-layout.ts)) walks the
sequence chain, so stop order is correct. But `buildSections`
([route-sections.ts:80-118](../../../../../frontend/lib/route-sections.ts)) buckets
**every** stop by `area_id` and emits the buckets in `area.order`:

| | order presented |
|---|---|
| **rail** | a1 → *Map the Problem contract*, *Write a minimal Problem subclass* · then a2 → *Understand the Graph data structure*, *Use GraphProblem*, *Use pre-built maps* |
| **`/advance`** | *Map the Problem contract* → *Understand the Graph data structure* → *Write a minimal Problem subclass* → *Use GraphProblem* → … |

The module's own docstring says "the stops keep the order `buildRoute` produced"
— true **within** a section, false **across** them whenever the planner
interleaves areas, which this 16-unit graph does throughout. So the reviewer's
reading of the order ("1. Problem contract, 2. build a subclass, 3. Graph") is
what the UI showed; the plan says otherwise. **F10 is therefore not a user
detour — the navigation surface presented that order.** The `why_now` in lesson 2
was written against the walk while the learner was following the rail.

**F20 — [FACT] The system marked a correct answer wrong, opened a blocking gap
against a true claim, and re-taught a fabrication.** Ground truth,
[search.py:1206-1215](../../../../../data/repos/aima-python/search.py):

```python
def h(self, node):
    locs = getattr(self.graph, 'locations', None)
    if locs:
        ...
    else:
        return np.inf
```

The learner wrote: *"it checks whether the graph has `locations`; if it does not,
the heuristic falls back to **`np.inf`**"* — correct, including the `getattr`
guard. What the system did with it:

| stage | what it produced |
|---|---|
| original lesson | hedged: the heuristic "will **either return 0** (admissible but useless) **or fail silently**" |
| Grader | `partial` / `wrong_model`; gap `5a3b067d…` opened with claim *"When locations is missing, GraphProblem.h() falls back to returning np.inf"*, `foundational=True`, `status=open` — **the gap records a true statement as a misconception** |
| re-teach | hardened the guess into an assertion: *"The GraphProblem code **must have** a safeguard. It **likely** does something like `if hasattr(...)`… the heuristic doesn't return infinity; **it returns 0**"* |

The hedging verbs are the tell: `must have`, `likely`. **Teaching was reasoning
about code it could not see** (F21) and asserted the result as a correction to a
learner who had read it.

**F21 — [FACT] Root cause: the objective demands a claim whose evidence lies
outside the unit's only anchor — third instance, first with measured harm.** The
objective ends *"…and explain why omitting `locations` breaks heuristic-based
search without raising an error"*. That behaviour lives in `GraphProblem.h`
(1206–1215); the unit's sole anchor is `Graph` (1006–1058). CLAUDE.md's *"no
source, no lesson"* rule is satisfied — the anchor **loaded fine** — so nothing
refused. The rule guarantees the model had *an* anchor, not that it had the
source for the claim the objective demanded.

This is the same shape as **F1** (`h` named in stop 1's objective, anchored on
`Problem`) and **F11** (stop 3 borrowing stop 4's whole anchor). F5 recorded that
F1 cost the learner nothing; **this one cost them a correct answer, a false
`foundational` gap, and a fabricated correction.** The lesson-1 [OPEN] — *should
an objective's named symbols be required to resolve within the unit's own
anchors?* — is no longer an open-ended tidiness question: **three firings, one
harmful.** It is now the strongest fix candidate in the round.

**F22 — [FACT] The same false claim is already sitting in a future unit's
objective.** Stop 15 ("Recognise the risk of missing or incomplete graph
definitions") states *"missing `locations` causes `h()` to return `np.inf` for
every node, **making A\* degrade to uniform-cost search** without error"*. The
first half is right (and is what the learner said). The second half is wrong: with
`h = inf` everywhere, `f = g + inf` is `inf` for **every** node, so the frontier
orders by `PriorityQueue`'s tie-break — `Node.__lt__` compares `self.state <
node.state` ([search.py:91-92](../../../../../data/repos/aima-python/search.py))
— i.e. by state, not by path cost. That is not uniform-cost search; it is
arbitrary order. Checkable now, before that unit is ever taught.

**[REC] on the reviewer's scope point.** The suggestion — add `GraphProblem.h` as
an explicit anchor, or move the heuristic question to the A* lesson — is the right
pair of options, and F20 shows the cost of doing neither. Note the two are not
equivalent: adding the anchor fixes *this* lesson; moving the question fixes the
unit boundary. **Still not acted on**, per the round's rule, but F20 is the first
finding here that would justify stopping the round to fix before continuing, and
that is the owner's call.

#### Lesson 3, second pass — the investigation the reviewer asked for

**Question raised:** *is the grader / re-teach generation actually receiving and
prioritising the exact source anchors used by the lesson, or is it relying on the
objective and expected-answer text? Source code should win whenever there is a
conflict.*

**Answered from the code. The finding is stronger than the hypothesis: on the
grading side there is no source in the room at all.**

**F23 — [FACT] The Grader never receives any source code.** `_build_user_content`
([grader/agent.py:367-383](../../../../../backend/agents/grader/agent.py)) assembles
the entire user message from:

| field | value sent |
|---|---|
| `LEARNING OBJECTIVE (the marking standard)` | `node.objective()` |
| node title, concept tags | strings |
| `Question` | `cached_lesson["prompt"]` |
| `Calibration reference (one phrasing, NOT the standard)` | `cached_lesson["expected_answer"]` |
| open gaps | claims recorded on the node |
| developer's response | the answer |

No anchors, no file, no lines, no `repo_path` — the Grader marks **text against
text**. So "source wins on conflict" is not a priority that is set wrongly; it is
**unimplementable as the call is currently constructed**. And because the
objective is explicitly designated *the marking standard*, **a false objective is
unfalsifiable**: no evidence can reach the call that could overturn it. That is
precisely what happened in F20 — the objective asserted "without raising an
error", the `expected_answer` asserted "returns 0", and a learner quoting the
repository was marked down by a call that had never seen it.

**F24 — [FACT] Teaching *does* get source, and the mechanism is sound; the scope
is what failed.** `_read_node_source`
([teaching/agent.py:329-360](../../../../../backend/agents/teaching/agent.py)) reads
**every** anchor in order and `_source_header` labels it; `reteach`
([respond.py:244-264](../../../../../backend/agents/teaching/respond.py)) takes a
`source` argument and injects it as *"The source code for this unit"*, fed from
`_node_source(graph, node)` at the call site
([api.py:928](../../../../../backend/api.py)). So the re-teach in F20 **did** hold
source — `Graph` 1006–1058 — which does not contain `GraphProblem.h`. It was
asked to correct a claim about code it had been handed the wrong pages for, and it
confabulated rather than declining. The two layers therefore fail differently:
**the Grader has no source by construction; Teaching has the unit's anchors and
no way to say "that is not in front of me".**

**F25 — [FACT] Verification cannot rescue a false gap either.** `_user_content`
([grader/verification.py:109-122](../../../../../backend/agents/grader/verification.py))
sends the objective, the gap claims under the heading **"OUTSTANDING FALSE
BELIEFS"**, the question and the answer — again **no source**. Gap `5a3b067d…`
records a *true* statement under that heading. So closing it requires the learner
to assert that `h` returns 0; a learner who repeats what the code says stays
`unresolved`, and `mark_verified` is reachable only by adopting the falsehood.
**The verification loop, which exists to prove a misconception is gone, would here
certify that a correct model had been replaced by a wrong one.**

**[REC] This reframes the round's leading fix candidate.** Up to F22 the candidate
was the plan-time check "do an objective's symbols resolve inside its own
anchors?". F23–F25 show that check is necessary but not sufficient: it would have
prevented this objective from being written, but it leaves both graders unable to
notice a false premise that reaches them by any other route. The two candidates
are complementary and should be judged together at the end of the round:

1. **plan-time** — an objective may not require evidence outside its unit's anchors (F1, F11, F21);
2. **grade-time** — the Grader and the verification grader receive the unit's anchor source, with an explicit instruction that source outranks the objective and the calibration reference on conflict (F23, F25).

Cost note for (2): it adds the anchor source to every grading call, which is a
real token increase on the per-answer path and belongs in
[`cost-optimization.md`](../../cost-optimization.md)'s accounting, not in a
footnote here.

#### The gap surface offers no way to say the system is wrong

**Observed on stop 2's lesson screen:** the *Still unresolved* list shows gap
`5a3b067d…` — a **true** statement (F20) — captioned *"Holding this stop back"*,
with exactly one control: **Set aside**.

**F26 — [FACT] Every action available to the learner records a false thing, and
none of them is "this gap is wrong".** The list renders one button per gap,
`t.lesson.waiveOne`
([LessonPanel.tsx:476-483](../../../../../frontend/components/LessonPanel.tsx)), plus
the verification box below it. Tracing each path for a gap that should never have
been opened:

| the learner can | what the code does | what the record then says |
|---|---|---|
| **Check my understanding** | verification graded with no source ([verification.py:109-122](../../../../../backend/agents/grader/verification.py)) | closes **only** if they assert `h` returns 0 — the falsehood (F25). Restating the code leaves it `unresolved` |
| **Set aside** | `waive_gap` ([graph.py:429-447](../../../../../backend/learning/graph.py)) — *"Never evidence: `waived` does not permit `understood`"* | *"you chose not to pursue this"* ([strings.ts:486](../../../../../frontend/lib/strings.ts)); the stop is capped below demonstrated **forever**, for an answer that was right |
| **nothing** | gap stays `open`, `blocking` | the stop is *"holding this stop back"* indefinitely |
| **mark understood** (override) | `understanding_of` is the single owner and *"`verified` is the only status that permits `understood`"* ([graph.py:189-215](../../../../../backend/learning/graph.py)) | no effect on the block |

**There is no truthful exit.** The gap lifecycle has states for *learner was
wrong and fixed it* (`verified`), *learner was wrong and stopped* (`waived`) and
*learner is still wrong* (`open`) — and **no state for "the system was wrong"**.
Every affordance presumes learner fault, so the one honest action is the one the
UI does not offer.

**[REC] The strictness is not the defect and should not be relaxed.** M7's rule
that only `verified` permits `understood` exists for a measured reason (loss
point 5: mastery reported over two open misconceptions), and waiving deliberately
buys silence rather than credit. What is missing is a **dispute path** — some way
for a learner to reject a claim, which would also be the highest-value signal this
system could collect, since a disputed gap is a labelled instance of exactly the
failure F20–F25 describe. Naming it is not designing it; the shape (does a dispute
delete the gap, flag it, or trigger a grounded re-check against the anchors?) is a
product decision that belongs with the other end-of-round calls.

**Note on the design comment.** [LessonPanel.tsx:456-459](../../../../../frontend/components/LessonPanel.tsx)
describes this list as *"the product's most honest surface: it tells the learner
what they still do not know, by name"*. That is true **only while the gaps are
true**, and F23 shows nothing at grading time can establish that. The most honest
surface in the product is currently displaying a correct statement as a
misconception, and inviting the learner to abandon it.

### Lesson 4 — "Use GraphProblem for map-based search" (stop 4)

| | |
|---|---|
| node | `0ba8f6d3affe45a6a91dd05879a30ff6` |
| kind / priority / area | `component` / `required` / `a2` |
| anchors | `GraphProblem` 1179–1215, **`GraphProblem.h` 1206–1215**, `GraphProblem.actions` 1186–1188 |
| outcome | lesson read, **not yet answered** (0 attempts) |

**Reviewer verdict:** the lesson is strong — objective, anchors and question well
aligned; the Sibiu `h()` question is correctly scoped, and *"unlike Lesson 3,
asking about the `np.inf` fallback belongs here because `GraphProblem.h()` is
explicitly one of the anchors"*. The issue is sequencing across stops 2–4, not
this unit.

**F27 — [FACT] The controlled comparison for F21 is sitting in this session's own
data, and it is decisive.** The same claim, same repository, same session, same
model, four minutes apart — the **only** difference is whether `GraphProblem.h`
was in the unit's anchor set:

| | stop 2 anchors | claim produced |
|---|---|---|
| stop 2 "Understand the Graph data structure" | `Graph` 1006–1058 — **`h` absent** | *"the heuristic doesn't return infinity; **it returns 0**"*, and a correct learner marked `wrong_model` (F20) |
| stop 4 "Use GraphProblem" | `GraphProblem` 1179–1215 **+ `GraphProblem.h` 1206–1215** | *"It returns **`np.inf`** when the graph has no `locations` attribute at all"* — **correct** |

This removes the last alternative explanation for F20. It was not model
variance, not prompt wording, not the objective's phrasing alone: **anchor
coverage determined whether the system told the truth.** The reviewer identified
the same boundary from the outside, from the lessons only.

**F27b — the residue, and it is consistent.** Stop 4's `expected_answer` still
ends *"falls back to uniform-cost-like behavior"* — the F22 error, softened by a
hedge. `h` returning `inf` **is** in this unit's anchors and is stated correctly;
what A\* then *does* lives in `best_first_graph_search` (search.py:260-287), which
is **not** anchored here, and that is exactly the half that is still wrong. The
same rule explains the correct half and the incorrect half of one sentence.

**F28 — [FACT] The dependency inversion the reviewer describes is visible in the
planner's own edges.** Declared prerequisites:

| unit | prerequisites the planner declared |
|---|---|
| stop 3 "Write a minimal Problem subclass" | `Map the Problem contract` **only** |
| stop 4 "Use GraphProblem for map-based search" | `Map the Problem contract`, `Understand the Graph data structure` |

So by the planner's own model, stop 3 needs neither `Graph` nor `GraphProblem` —
yet **stop 3 is anchored on `GraphProblem` 1179–1215** (F11) and its `setup`
teaches `graph.get()` and the adjacency structure. The sequence order 3-before-4
is *consistent with the declared edges*; the edges simply under-declare what the
unit actually teaches from. **A unit's anchors reach outside its own prerequisite
closure**, which is the mechanical form of "dependency inversion" and is
checkable without a model.

Two complementary plan-time checks now converge, and neither needs an LLM:

1. an objective must not require evidence outside its unit's anchors (F1, F11, F21, F27);
2. a unit's anchors must lie within symbols owned by that unit or by its declared prerequisite closure (F28).

**[REC] The reviewer's reordering is a real improvement to the plan, not only to
what was experienced.** Proposed: `Problem` contract → `Graph` → `GraphProblem` →
write your own subclass. Against the current plan that is a single swap of stops 3
and 4, and it dissolves F11 at the source: with the worked example first, stop 3
no longer needs to borrow `GraphProblem`'s anchor, and the sliding-puzzle question
becomes a genuine transfer exercise rather than a paraphrase of an example the
learner has just been shown. **Recorded, not applied** — it is a planner-prompt or
ordering-heuristic change and belongs with the end-of-round decisions.

**Note on `why_now` here — it is correct.** *"Now that you've built a minimal
Problem subclass"* matches both the plan and what the learner actually did (stop 3
answered `understood` before reaching stop 4). F10's failure mode does not recur
when the walk and the learner agree.

#### Lesson 4, second pass — deliberately wrong answer, correct verdict, wrong correction

**Reviewer method:** an intentionally wrong answer, to test grading separately
from teaching. **Verdict correct** (`confused` / *Not yet*): both planted errors
were caught — `h()` reading edge weights rather than `locations` coordinates, and
the missing-`locations` fallback being `0` rather than `np.inf`. Two gaps opened,
both recording genuinely false claims. **But the re-teach introduced a new
conceptual error**, and the reviewer's hypothesis was that the old
uniform-cost conclusion *survived* the `np.inf` correction — i.e. the re-teach may
not be regenerating its reasoning from grounded facts.

**F29 — [FACT] The conclusion did not survive. It was regenerated from nothing,
and that is the stronger result.** The re-teach prompt is built by `_node_context`
([respond.py:175-187](../../../../../backend/agents/teaching/respond.py)) from **this
node only**: objective, question, the learner's answer, the grader's rationale,
the gap block, and `lesson.get('setup') or lesson.get('walkthrough')`. There is no
cross-node carrier, and every input was checked:

| input to the re-teach | contained "uniform-cost"? |
|---|---|
| grader rationale | **no** — *"…claims h() returns 0 instead of np.inf"* |
| gap claims (both) | **no** — edge-weights claim, and returns-0 claim |
| prior lesson `setup` (the branch actually taken) | only correctly, about `path_cost`: *"This respects the actual distances, not uniform cost"* |
| prior `expected_answer` (*not passed* — `setup` wins the `or`) | yes, but it never reached the call |

So the erroneous conclusion was in **none** of the re-teach's inputs and appeared
in its output anyway: *"The algorithm will still run, but it defaults to
uniform-cost behavior without actually being smart about it."*

Counting every independent generation of this claim in one session:

| # | produced by | text |
|---|---|---|
| 1 | Teaching, stop 2 lesson | "degrades to uniform-cost search" |
| 2 | Teaching, stop 2 re-teach | "returns 0 … degrades to uniform-cost search" |
| 3 | Teaching, stop 4 lesson | "falls back to uniform-cost-like behavior" |
| 4 | Teaching, stop 4 re-teach | "defaults to uniform-cost behavior" |
| 5 | **the planner**, stop 15 objective | "making A\* degrade to uniform-cost search" (F22) |

**Five generations, three call sites, two nodes, no shared state.** This is a
model prior about A\* filling the space where the anchors stop: `h` is anchored at
stop 4 and is stated correctly, while what A\* *does* with `h` lives in
`best_first_graph_search` (search.py:260-287), which is anchored **nowhere in this
journey**. The consequence for fix design is direct: **correcting this claim in
any one place cannot work.** The plan-time objective check (F21/F28) would not
have removed it either, because it arises in Teaching's prose about consequences,
not in the objective. Only anchoring the consumer — or refusing claims about code
outside the anchors — reaches it.

**F30 — the second overgeneralization is the same rule again.** *"GraphProblem
works as-is only when your graph has a `locations` dictionary."* As the reviewer
notes, only the built-in **heuristic** needs `locations`: `breadth_first_graph_search`
and `uniform_cost_search` never call `h()`, and `astar_search(problem, h=...)`
accepts one explicitly. Those functions are, again, **outside stop 4's anchors**.
Three claims in one re-teach: the anchored one (`h` → `np.inf`) correct, the two
unanchored ones (what A\* does, what `GraphProblem` requires) both wrong.

**[REC] Grade correctness and re-teach correctness must be measured separately —
the round now has a case that separates them cleanly.** Stop 4: **grading right,
teaching wrong**. Stop 2 (F20): **grading wrong, teaching wrong**. The two failure
modes have different causes (F23: the Grader has no source at all; F21/F29:
Teaching has *some* source and no way to decline beyond it) and would need
different fixes. Any future evaluation that reports a single "lesson quality"
number would average these two into one uninterpretable figure.

### The warm-up generated after lesson 4's failure

| | |
|---|---|
| node | `ceb9b6e7547748cf85eb3be5276b022e`, inserted 20:01:42, `origin: learner_request`, unlocks stop 4 |
| title | *"Understand how **GraphProblem.h** uses the locations dict for straight-line distance"* |
| objective | *"I can state that **path_cost** delegates edge-weight lookup to `graph.get(A, B)` and returns `np.inf` — not 0 — when no edge exists…"* |
| display anchor | `search.py` **`GraphProblem.path_cost` 1194–1195** |
| `lesson_brief` keys | `objective`, `why`, `understand`, `priority`, `origin` — **no `remediates`**, **no `anchors`**, no `kind`, no `area_id` |
| outcome | answered, graded `understood`; **both stop-4 gaps still `open`** |

**Reviewer verdict:** right conceptual neighbourhood, partial repair. The title
says `h()` while the exercise is about `path_cost()`; the second misconception
(missing `locations` → `h` returns `0`) is never tested, so passing this warm-up
is not evidence the original failure is fixed.

**F31 — [FACT] The warm-up was never aimed at either gap, and the code says so.**
`/retry` calls `mutate_graph(state, "prerequisite", origin=LEARNER_REQUEST)` with
**no diagnosis** ([api.py:1039-1041](../../../../../backend/api.py)), so the Mutator
rebuilds one via `Diagnosis.from_node`
([mutator.py:100-133](../../../../../backend/agents/mentor/mutator.py)), which
attaches a `Gap` **only if** `decide_all(...).action == "prerequisite"`. Both
stop-4 gaps are `wrong_model`, whose policy action is **`reteach`** — so
`gap is None`, `remediates` is omitted
([mutator.py:482-483](../../../../../backend/agents/mentor/mutator.py)), and the
warm-up is, in the source's own words, *"aimed by the answer rather than"* by a
gap. The reviewer's conclusion — *the warm-up should be derived from the specific
misconceptions detected, not from a nearby prerequisite concept* — is therefore a
**designed consequence**, not a generation failure: §18.5 caps structural
mutation at one gap per answer, and here it designated none.

**F32 — [FACT] The `np.inf` in the warm-up is a different `np.inf`.** The
objective's *"returns `np.inf` — not 0 — when no edge exists"* is
`path_cost`'s missing-**edge** case (`self.graph.get(A, B) or np.inf`,
search.py:1194-1195). The learner's gap is `h`'s missing-**locations** case
(search.py:1206-1215). Same constant, different method, different trigger. This is
worse than not addressing the misconception: the warm-up rehearses "the answer is
`np.inf`, not `0`" **about the wrong function**, which is precisely the
`path_cost`/`h` conflation the learner already had.

**F33 — [FACT] Title and objective contradict each other inside one generation.**
The title is about `h`; the objective, the anchor and the whole question are about
`path_cost`. Nothing plumbs these separately — the prerequisite prompt returns
them together — so this is the same internal-inconsistency shape as F2, F7 and
F16, now in the Mutator. Since the objective is the marking standard (F23), **the
learner is graded on `path_cost` under a heading promising `h`.**

**F34 — [FACT] Mutator-created nodes are born in the pre-B3 shape.** The warm-up
carries `understand` — the field CLAUDE.md records as *"not emitted by the
objective-first planner… survives only on pre-B1/B3 graphs"* — and `anchors` is
**null**, so the invariant *"the display columns always equal one member of
`anchors`"* is vacuous on it, and `_read_node_source` takes its documented
absent-anchors fallback. Teaching still gets source, so nothing broke here; but
every structural mutation writes a node the rest of the system treats as legacy.

**Credit where the design held.** Passing the warm-up did **not** close either
gap — both remain `open` on stop 4, and the node was graded `understood` on its
own objective only. That is exactly right: only verification closes a gap
(gap-model M6), so an unaimed warm-up cannot launder itself into evidence. The
reviewer's test — *"if the learner passes this, do we have evidence the original
misconceptions are resolved?"* — is answered **no** by the system's own
bookkeeping as well as by inspection.

**[REC] and a prediction worth checking at the end of the round.** M3b's
`remediation_closure` template counts warm-ups carrying `remediates`, and the
phase recorded **0 such links across every database**. F31 explains why and
predicts it will stay 0 for every learner-requested warm-up whose leading gap kind
maps to `reteach` — i.e. for `wrong_model`, the most common kind observed in this
session. **That template may be uncomputable in practice rather than merely
data-poor**, which is a different problem from the one M3b recorded.

### After the warm-up succeeds — the corrective lesson never stands down

**Reported:** having answered the warm-up correctly, the feedback still says
*"You just assigned the wrong responsibility—edge weights go to `path_cost`, not
to `h`"*, which is a mistake the learner did **not** make in that answer; the
explanation largely repeats the lesson-4 correction; and both earlier technical
errors are still present.

**F35 — [FACT] Nothing was generated after that answer. The text is the parent
node's stored lesson, and the learner had walked back into it.** The warm-up's
own attempt records `classification: understood`, `gap_kind: none`,
`response: {"action": "none"}` — the adaptation policy produced **no** new text.
Passing the warm-up then advances along the prerequisite edge back to stop 4
(the F1 return), and stop 4's `cached_lesson` **is the re-teach**, written at
20:01 in response to the wrong answer:

> **ownership** — *"You have the right instinct that GraphProblem delegates some
> work to the Graph. **You just assigned the wrong responsibility**…"*
> **setup** — *"**You may have mentally merged them** because both relate to
> distance…"*

So the hypothesis — that warm-up feedback is over-conditioned on the parent
failure or the stored gap — is **not** what happened: no post-answer generation
occurs on `understood` at all. The observation is exactly right and the mechanism
is different, which changes the fix.

**F36 — [FACT] `reteach` replaces the lesson permanently, and the replacement is
written in the second person about one past answer.** From its docstring:
*"Replaces `cached_lesson` — the corrected lesson is the lesson now, and a
learner who returns should not meet the version that misled them"*
([respond.py:249-254](../../../../../backend/agents/teaching/respond.py)). The first
half of that reasoning is sound — the misleading original should not come back.
The unexamined half is that **the corrective version is equally permanent**, and
it is addressed to a learner state that expires: after the warm-up, after the
gaps close, on resume next week, stop 4 will still open by telling the learner
they assigned the wrong responsibility. There is no re-render on remediation
success and no non-accusatory version to fall back to. **The lifecycle the
reviewer describes — failed → warm-up → corrected → still told you were wrong —
is produced by a durable second-person artifact, not by a conditioning bug.**

**[REC]** Two separable questions, and only the second is a real design choice:
should a corrective lesson be phrased about the **misconception** rather than
about the **learner** (cheap, and it makes durability harmless); and should
stop 4 re-render once its gaps are verified (costly — another Teaching call —
and it discards the corrective framing that may still be the most useful version
while the gaps are open).

**F37 — [FACT] The two unanchored errors are now frozen into the node.** Stop 4's
stored `reveal` carries *"The algorithm will still run, but it defaults to
uniform-cost behavior"* (F22/F29) and the surrounding text still implies
`GraphProblem` is unusable without `locations` (F30, softened here to "cannot
function for this graph"). Because the re-teach is the lesson now, these are not
transient outputs the learner saw once: **they are what this node renders on every
future visit and on resume**, and they sit beside a correct, well-anchored
account of `h`. This is the first place in the round where earlier findings
compound — a confabulation about unanchored code (F29) became durable through a
mechanism designed for a different purpose (F36).

**State at this point, for the record.** Stop 4: 2 attempts, latest `understood`,
**both gaps still `open`** — so `understanding_of` correctly withholds
`understood` and verification is the way out. Unlike stop 2's false gap (F26),
these two gaps record genuinely false claims the learner has since corrected, so
here the verification path is the appropriate one and the design works as
intended.

### The rail after a correct re-answer — "◇ 2 unresolved", unchanged

**Reported:** stop 4 still reads *"◇ 2 unresolved"* after being re-answered
correctly. Documented only.

**F38 — [FACT] Nothing is wrong with the count; the state vocabulary has no word
for what the learner just did.** The wire sends **open gaps only**
([graph.py:764-772](../../../../../backend/learning/graph.py)), so "2" is accurate,
and `understanding_state` is the *derived* value, correctly withholding
`understood` while two blocking gaps are unverified. The rail renders
`unresolvedCount(gaps.length)` for every `unresolved` node carrying gaps
([RouteRail.tsx:190-191](../../../../../frontend/components/RouteRail.tsx)).

What that collapses is two states a learner would never call the same thing:

| | rail says |
|---|---|
| never reached the objective, 2 misconceptions open | ◇ 2 unresolved |
| **latest answer reached the objective**, 2 checks not yet taken | ◇ 2 unresolved |

**The distinguishing signal already exists and is already on the wire** —
`attempts` (so `attempts[-1].classification == "understood"`) and the evidence
chain's `state_matches_latest_answer`. Neither surface uses it for this case:

- the **rail** never consults it;
- the **drawer** gates `pendingVerification` behind `chain.understanding !== "unresolved"` ([EvidenceDrawer.tsx:115-116](../../../../../frontend/components/EvidenceDrawer.tsx)), which excludes exactly this node;
- the four `why…` sentences cover *check waiting*, *waived*, *gaps open*, *answer fell short* ([strings.ts:583-597](../../../../../frontend/lib/strings.ts)) — **none covers "your latest answer was right, the gaps are simply unverified"**, so stop 4 falls to `whyOpenGaps(2)`: *"2 misconceptions are still open here."*

**Why this is worth recording rather than shrugging at.** M9's browser pass fixed
the *wrong* caption here (`⚑ marked weak` for a learner whose latest answer
reached the objective) and replaced it with an accurate one — but accuracy was
only half the requirement. The learner corrected the misconception, answered
correctly, and **every visible surface reports exactly what it did before.** With
F26 (no way to say the system is wrong) this is the same shape twice: the state
model represents what the *system* concluded and has no vocabulary for what the
*learner has since done*.

**[REC]** The cheapest honest change is one string and one condition, not a model
change: the rail and the drawer already receive everything needed to say "your
last answer reached this — 2 checks left". Whether the count should also become
"2 checks" rather than "2 unresolved" once the latest answer is `understood` is a
copy decision for the end of the round.

### Lesson 5 — "Use pre-built maps" (stop 5)

| | |
|---|---|
| node | `4f905892351844b7ae4230e7fa4ef710` |
| kind / priority | `component` / `recommended` |
| anchors | `search.py` `GraphProblem` 1179–1215 · **`tests/test_search.py` `test_astar_search` 78–83** |
| outcome | answered once, `understood` |

**Reviewer verdict:** right topic, but the lesson blurs the `Graph` passed to
`GraphProblem(...)` with the already-constructed `romania_problem`, and never
anchors where the latter is created — a repository-grounded lesson should show
that definition rather than have the learner infer it. Separately, the wording
implying all three data pieces are equally needed "to produce that specific
solution" overstates the heuristic's role.

**F39 — [FACT] Everything the lesson says is "not shown" was inside files it had
already opened, a few dozen lines outside the anchor window.** The lesson's own
prose admits the hole and asks the learner to fill it:

> *"`romania_problem` is created somewhere **(not shown in this code)**…"*

Where those definitions actually live:

| symbol the lesson discusses | where it is | anchored? |
|---|---|---|
| `romania_problem` | **`tests/test_search.py:6`** — same file as the anchor, **72 lines above** it | ✗ |
| `romania_map` | `search.py:1099-1112` (+ `.locations` at 1113) | ✗ |
| `australia_map` | `search.py:1169` | ✗ |

Both files were already being read: the anchor set names `search.py` and
`tests/test_search.py`. **The system anchored a six-line window of a file and
then told the learner that a definition seventy lines up in that same file could
not be shown.** The objective compounds it — *"Identify the pre-built Graph
objects available (`romania_map`, `australia_map`)"* — naming two symbols,
neither anchored.

This is the **fourth** instance of the F21 pattern (after F1, F11/F28, F27) and
the first where the lesson **states the gap out loud** rather than confabulating
across it. That is a meaningfully better failure — inference invited is not
fabrication asserted — but it is the same root cause, and it makes the plan-time
check (objective symbols ⊆ unit anchors) look under-specified: here the symbols
are in the *right files* and outside the *line ranges*. A useful check has to be
range-aware, not file-aware.

**Worth noting as a good behaviour:** anchoring a **test** as a usage example is
exactly right for a `use_library` goal — `tests/test_search.py` is where the
runnable five-line pattern lives. The selection of the window is what failed, not
the decision to go there.

**F40 — the "all three" wording, and a repo-specific twist the reviewer's
correction exposes.** The lesson says A\* *"needs all three: edges to know
traversal costs, neighbors to expand the frontier, and locations to guide the
search toward Bucharest"*. The reviewer's decomposition is the correct one:
adjacency defines which successors exist, edge costs contribute to `g(n)`, and
`locations` feed `h(n)` — and a heuristic guides **order**, it does not define
connectivity or path cost.

The twist: in **this** implementation the generic story does not hold either.
Missing `locations` makes `h` return `np.inf` (F27), so `f = g + inf` is `inf`
everywhere and the frontier orders by `Node.__lt__` on state (F22) — not "less
efficient but still correct", which is what standard A\* reasoning would predict.
So the lesson is wrong in one direction (overstating what `locations` contribute
to *correctness of the path definition*) while the generic correction would be
wrong in the other (understating that here, losing `locations` really does break
the result). **Both errors come from reasoning about A\* in general rather than
about `best_first_graph_search` in particular — the same unanchored prior behind
F22 and F29.**

**[REC]** The reviewer's proposal — anchor the construction chain
(`romania_map` → `GraphProblem(initial, goal, romania_map)` → `romania_problem` →
`astar_search(...)`) and teach it as a trace — is a better lesson *and* removes
the inference. It also happens to be the `flow` unit kind the planner already
supports, on a unit currently typed `component`.

#### Lesson 5, second pass — and the round's missing control case

**Reviewer verdict:** verdict correct and well-reasoned; and the post-answer
explanation *"`romania_problem` is a pre-built instance of `GraphProblem` created
with `GraphProblem('Arad', 'Bucharest', romania_map)`"* is exactly the relationship
the lesson should have anchored rather than left to inference. Two wording points:
the "needs all three" framing again conflates problem definition with heuristic
guidance, and "node names" is less precise than adjacency/connectivity.

**F41 — [FACT] That sentence is verbatim correct and was in none of the model's
inputs. It is an unanchored claim that happened to be right.** Ground truth is
`tests/test_search.py:6`:

```python
romania_problem = GraphProblem('Arad', 'Bucharest', romania_map)
```

Checked against everything the call received:

| input | contains the construction? |
|---|---|
| anchor 1 — `GraphProblem` 1179–1215 | no |
| anchor 2 — `test_astar_search` **78–83** (the fixture is at line **6**) | no |
| `doc_context` | **no** — `romania_map` 0 occurrences, `GraphProblem(` 0 occurrences; the single `romania_problem` hit is the unrelated `gui/romania_problem.py` file-docs entry |

So Teaching reproduced a line from `aima-python` — one of the most widely mirrored
teaching repositories in existence — **from prior knowledge, not from evidence.**

**This is the control the round was missing.** F29 established that claims beyond
the anchors get confabulated; F41 establishes that they are *sometimes exactly
right*, by the same mechanism, with nothing in the output distinguishing the two:

| | claim beyond the anchors | outcome |
|---|---|---|
| F20 / F29 | `h` returns 0; A\* degrades to uniform-cost | **wrong** — cost a learner a correct answer |
| F41 | `GraphProblem('Arad', 'Bucharest', romania_map)` | **right** — and reads as the most grounded sentence in the lesson |

**Three consequences worth carrying to the end of the round.**

1. **"The lessons mostly look good" is not evidence of grounding.** Most
   unanchored claims about a famous repository will be correct, so the failures
   are rare, confident, and embedded in accurate material — the hardest possible
   error profile to notice.
2. **This session's error rate is a lower bound, and `aima-python` is close to a
   best case.** On a private repository, an unusual codebase, or the multi-language
   work in [`multi-language.md`](../../multi-language.md), the same mechanism has
   no correct prior to fall back on. Nothing measured here transfers to those
   without re-measuring.
3. **It sharpens the reviewer's recommendation.** Moving the construction into the
   lesson's anchors is not only better pedagogy — it converts a lucky guess into a
   grounded fact, and is the difference between a lesson that is right and a
   lesson that is right *for a reason the system can defend*.

**F42 — the two wording points, both confirmed, both small.** The `g`/`h`
conflation ("needs all three to function correctly and efficiently") is the same
claim as F40, recurring in the post-answer summary — recorded as a recurrence, not
a new finding. On terminology: `GraphProblem.actions` is
`list(self.graph.get(A).keys())`, so what it requires is the **state → neighbours
mapping**; node names are a by-product of that dict's keys, and `Graph.nodes()` is
a separate reconstruction. "Adjacency/connectivity" is the more accurate of the
two, as reported.

### Lesson 6 — "Call astar_search and read the result" (now stop 7)

> Positions shifted by one from here on: the warm-up was inserted at stop 4, so
> the walk is now 17 units.

| | |
|---|---|
| node | `0c0d9080db764e99bf8cb53eab9d35c5` |
| anchors | `astar_search` 415–420 · `Node.solution` 105–107 · `tests/test_search.py::test_astar_search` 78–83 |
| outcome | answered once, `understood` |

**Reviewer verdict:** good placement, objective and anchors; the Node-not-a-list
distinction is valuable and bridges cleanly to the later `Node` unit. Two points:
the question's "protects or exposes" wording should ask directly what happens when
`.solution()` is chained onto `None`; and the no-path behaviour may not be
grounded, since `astar_search` delegates.

**This is the best-grounded lesson of the round, and it is the reviewer's second
point that makes it worth recording.**

**Everything inside the anchors is exactly right** — verified line by line:

| claim | source | verdict |
|---|---|---|
| `Node.solution()` returns `[node.action for node in self.path()[1:]]` | search.py:105-107 (**anchored**) | verbatim correct |
| the solution is `['Sibiu', 'Rimnicu', 'Pitesti', 'Bucharest']` | tests/test_search.py:79 (**anchored**) | quoted exactly |
| `GraphProblem.result()` returns the neighbour name, so actions are names | search.py:1191-1193 | correct |
| chaining `.solution()` on `None` raises `AttributeError` | Python semantics | correct |

**F43 — [FACT] The one claim resting outside the anchors is the `None` return,
and the reviewer identified it without seeing the anchor list.** `astar_search`
(415–420) only delegates: `return best_first_graph_search(problem, f, display)`.
The `return None` is the last line of `best_first_graph_search`, **search.py:287**
— not anchored here. Fifth instance of the F21 pattern; this time the claim is
**correct**, which is exactly what F41 predicts for a repository the model knows.

**F44 — [FACT] One missing anchor accounts for four separate findings.**
`best_first_graph_search` 260–287 is anchored on **five** units — stops 10, 12,
13, 14 and 15 — and on **none** of stops 2, 5, 6 or 7, which are precisely where
every claim about it was made:

| unit | claim about `best_first_graph_search` | anchored there? | outcome |
|---|---|---|---|
| stop 2 *Understand the Graph data structure* | "degrades to uniform-cost search" | ✗ | **wrong** (F20) |
| stop 5 *Use GraphProblem* | "defaults to uniform-cost behavior" | ✗ | **wrong** (F29) |
| stop 6 *Use pre-built maps* | "A\* needs all three… to produce that specific solution" | ✗ | **wrong** (F40) |
| stop 7 *Call astar_search* | "returns `None` when no path exists" | ✗ | right, by luck (F43) |
| stop 16 *risk of incomplete graph definitions* (objective) | "degrade to uniform-cost search" | ✗ | **wrong** (F22) |

The function the early curriculum reasons about constantly is first anchored at
*"Trace the A\* runtime flow end-to-end"* — **after every one of those claims has
already been made and, in four cases, made wrongly.** This is F28's
dependency-inversion measured a second way, and it gives the plan-time check a
concrete acceptance test: *a symbol a unit makes claims about must be anchored on
that unit or on an earlier one.* Applied to this journey it fires five times and
would have caught F20, F22, F29 and F40.

**On the question wording:** the reviewer's rewrite is better and the current
phrasing is genuinely loose — "protects or exposes you" invites a yes/no where the
useful answer is the guard pattern. Noted as a prompt-quality point, not a defect.

#### Lesson 6, second pass — the tightest anchor miss in the round

**Reviewer verdict:** verdict and most of the explanation are right; one causal
claim is wrong — *"`GraphProblem.result()` returns the neighbor node name, and
that name becomes the action recorded in the child Node"* / *"that's what
`GraphProblem.result()` stores as the action in each Node"*. `result()` does not
store anything; `Node.child_node()` receives the action, uses `result()` to
compute the next **state**, and stores the two separately.

**F45 — [FACT] Confirmed, and the disambiguating code sits two lines above the
anchor window.** search.py:94-103:

```python
def expand(self, problem):                                   # 94
    return [self.child_node(problem, action)
            for action in problem.actions(self.state)]       # 97  ← action originates HERE

def child_node(self, problem, action):                       # 99
    next_state = problem.result(self.state, action)          # 101 ← result() makes the STATE
    next_node = Node(next_state, self, action, ...)          # 102 ← state and action stored separately
```

The action recorded on a `Node` is the one `problem.actions()` produced, threaded
through unchanged. `result()`'s return value becomes `next_state`, the first
positional argument. For `GraphProblem` both are `'Sibiu'` — a coincidence of that
adapter, since its `actions` returns neighbour names and its `result` returns the
action it was given — which is exactly why the conflation is invisible on this
repository and false in general.

This unit's anchors are `astar_search` 415–420, **`Node.solution` 105–107**, and
the test 78–83. `child_node` ends at **line 103**. **The evidence that would have
prevented the error is two lines above the anchor start, in the same class, in the
same file** — sixth instance of the F21 pattern and the tightest by an order of
magnitude. It also strengthens F39's point: a file-level check is useless here, and
even a symbol-level one passes (`Node.solution` *is* anchored). What fails is that
the lesson reasoned about `Node`'s **construction** while anchoring only `Node`'s
**accessor**.

**F46 — [FACT] The error erodes a distinction an earlier unit taught correctly.**
Stop 3 ("Write a minimal Problem subclass") states, in both `reveal` and
`expected_answer`, that `result` "must return the *new state* … not a Node" — and
the reviewer recorded that as one of the round's genuinely good teaching moments.
Stop 7 then tells the same learner that `result()` supplies the *action*. Nothing
reconciles them, and the later unit is the wrong one. This is the F12/F16
cross-unit inconsistency family in a new and worse direction: **not two units
disagreeing at the same altitude, but a later unit dismantling a correct
distinction an earlier one established.** No mechanism in the system compares a
unit's claims against what earlier units taught.

**[REC]** F45 is the strongest argument yet that the plan-time check must be
**range-aware and claim-aware**, not file- or symbol-aware (F39, F44). A rule of
the form *"a symbol the prose names must be anchored on this unit or an earlier
one"* would still have passed this lesson, because the named symbols
(`GraphProblem.result`, `Node`) are both anchored somewhere. What would catch it
is narrower and harder: the prose asserts a **data-flow relationship** between two
symbols, and the anchor set contains neither the function that implements it nor
its call site.

### Lesson 7 — "Choose between search algorithms" (stop 8)

| | |
|---|---|
| node | `03d7032f5b874e94afab7a7b9d831eba` |
| anchors | `astar_search` 415–420 · `breadth_first_graph_search` 238–257 · `tests/test_search.py::test_breadth_first_graph_search` 24–25 |
| outcome | answered once → `partial`; **the text below is the re-teach** |

**Reviewer verdict:** right objective and placement; but `uniform_cost_search` is
never anchored though the objective names it; optimality claims need their
heuristic assumptions, and admissibility may not have been taught yet; and the
"what does astar_search own / not own" question is more abstract than an
algorithm-selection objective needs.

**F47 — [FACT] `uniform_cost_search` is unanchored, the lesson says so out loud,
and anchoring it would have cost three lines.** The objective names all three
algorithms. Anchored: `astar_search` (a 6-line delegating stub) and
`breadth_first_graph_search`. Missing: `uniform_cost_search`, **search.py:290-292**:

```python
def uniform_cost_search(problem, display=False):
    """[Figure 3.14]"""
    return best_first_graph_search(problem, lambda node: node.path_cost, display)
```

That one lambda **is** the lesson's central claim — UCS orders by accumulated cost
rather than hops — and it is the cheapest possible anchor in the round. Instead the
lesson writes *"Uniform_cost_search (which exists in the codebase but you haven't
seen yet)"*. Seventh instance of the F21 pattern, and the **second** where the
prose admits the hole rather than confabulating across it (after F39). The claims
that *are* anchored are, as ever, exact: `frontier.popleft()` is FIFO
(search.py:250), and there is genuinely no `path_cost` in BFS's comparison logic.

Note the compounding: UCS's behaviour is itself `best_first_graph_search`, the
function F44 showed is anchored nowhere before stop 10.

**F48 — [FACT] The lesson's optimality condition is correct and uses a term the
journey has not defined yet.** The objective and `expected_answer` both say *"A\*
when you have an **admissible** heuristic"* — properly conditioned, and the
reviewer's concern about unconditional optimality claims does **not** materialise
in the text. What does materialise is ordering: *"Understand the heuristic contract
for A\*"* — the unit whose objective is *"Explain what an admissible heuristic is
(never overestimates true cost)"* — is **stop 11**, three stops later. So the
learner is asked to select algorithms on a precondition they have not been taught
to evaluate.

This is F28/F44's dependency inversion at the **concept** level rather than the
symbol level, and it is not detectable by any anchor-based check: `admissible` is
not a symbol, so nothing resolves it. A concept-ordering check would need
`concept_tags` (which exist) to be treated as a dependency the way anchors are —
a bigger change, and one worth recording as a distinct problem rather than folding
into the anchor work.

**F36 recurs.** This unit's stored lesson is a re-teach and is therefore permanent
and second-person: *"You wrote: 'BFS guarantees the shortest path…'"*, *"You gave
up cost-optimality without naming it."* Every future visit to stop 8 opens with
that, exactly as stop 5 does.

**[REC] The reviewer's replacement question is better and is cheap.** Three
scenarios — unit-cost; weighted with no heuristic; weighted with a usable
heuristic — asking which algorithm and why, tests the stated objective directly,
whereas "what does `astar_search` own and deliberately not own" tests a different
and more abstract skill. Recorded as a `prompt_kind`/question-design point: the
unit is typed `architecture`, whose pedagogical form is what produced the
ownership framing, so this is an argument about form selection rather than about
this one prompt.

#### Lesson 7, second pass — three misconceptions in, one gap out

**Reviewer method:** an intentionally plausible wrong answer carrying several
separable errors. Verdict `partial` is reasonable; the issue is what was detected.

The submitted answer contained **three** separable false claims:

| # | claim in the answer | detected? |
|---|---|---|
| 1 | *"BFS … therefore guarantees the shortest path"* | ✅ gap `710552d6…`, `wrong_model`, `foundational=True` |
| 2 | *"A\* guarantees the optimal path **as long as a heuristic is available**"* | ❌ |
| 3 | *"What it does not do is work without a heuristic"* | ❌ — **and repeated by the re-teach** |

**F49 — [FACT] This is gap-model §18.1's founding defect, reproduced live: one
answer, several misconceptions, one survivor.** Exactly one gap was opened
(`gaps_opened: ['710552d6…']`). It is the correct one and the corrective teaching
on it is good — hop- vs cost-optimality, grounded in `frontier.popleft()`. The
other two were never recorded, so nothing downstream will ever come back for them.

**This miss is *not* explained by the round's anchor thesis, and that matters.**
Unlike F20, the information needed was already in the marking standard: the
objective says *"astar_search (**admissible** heuristic available…)"* and the
`expected_answer` says *"A\* when you have an **admissible** heuristic"*. The
Grader held the correct condition and still did not flag "as long as a heuristic
is available" as a misconception. So this is detection recall, not grounding —
and it matches **gap-model recorded limitation #1** ("AC1 detection variance on
AIMA — the second, subtler misconception is noticed 2/3 of the time") and M10's
measured 1-of-4 on this repository.

**The bar that phase set for reopening has now been met.** `gap-model.md` states:
*"No further Gap Model work should happen on any of these until a real learner
session shows it materially affecting learning."* This is a real session, and the
harm is concrete rather than theoretical — see F50. Recorded as met; whether to
act is the owner's call.

**F50 — [FACT] The re-teach repeats an undetected learner error, and F36 makes it
permanent.** The re-teach's `ownership`:

> *"astar_search: **requires admissible h**, promises cost-optimal path (caller
> gives up: speed if h is weak; **cannot work without heuristic**)."*

One sentence that both knows the correct condition and restates the learner's
claim #3. Because `reteach` replaces `cached_lesson` outright (F36), **stop 8 now
permanently teaches a misconception the learner arrived with.** That is a new
failure mode for this round: previous cases had the system inventing errors (F20,
F29); here it adopted one.

**The precise truth, since neither the answer nor the lesson states it:** A\* in
this repository requires *an* `h` to exist — `astar_search` does
`h = memoize(h or problem.h, 'h')` (search.py:419), so omitting it on a `Problem`
with no `h` attribute raises `AttributeError` (F6). But `h` **may be supplied by
argument**, and `astar_search(problem, h=lambda n: 0)` is legitimate and is
exactly `uniform_cost_search`. So "must supply some `h`" is true and "needs
heuristic guidance to function" is false; the lesson collapses them.

**F51 — two smaller items, both confirmed.**

- *"uniform_cost_search … (slower than A\* because it lacks guidance)"* is stated
  unconditionally. `uniform_cost_search` and `astar_search` are **the same
  function** with different `f` (search.py:290-292 vs 415-420); with `h=0` they are
  identical, and a weak or misleading `h` can make A\* slower. Not a property of
  either algorithm.
- The Grader's own rationale contradicts its own finding: *"grasps the core
  selection criteria (heuristic availability, **cost vs. hop optimality**) but
  conflates 'shortest path' with 'shortest-hop path'"* — it credits the exact
  distinction the gap it opened says was missed. Same internal-inconsistency shape
  as F2/F7/F33, now in the Grader's rationale rather than in a lesson.

#### "Build me a warm-up" declined on stop 8 — and the reason is destroyed

**Observed:** *"We couldn't build a warm-up for this one, so it's your call how to
continue."* Three `POST /retry` calls in the log, all **200 OK** — no exception,
node count unchanged at 17.

**F52 — [FACT] The Mutator records why, and three layers throw it away.**
`_mutate_prerequisite` ([mutator.py:241-284](../../../../../backend/agents/mentor/mutator.py))
sets `state.last_mutation` to one of **three materially different** outcomes:

| reason | meaning |
|---|---|
| `prerequisite_exists` | already warmed up here — a cap, not a judgement |
| `no_useful_prerequisite` (+ `rationale`) | **a real answer**: candidates were offered, none was a smaller foundation |
| `generation_failed` | the call failed or produced nothing groundable — **an error** |

Then: `/retry` returns only `{"current_node_id", "inserted": false}`
([api.py:1053-1055](../../../../../backend/api.py)) — reason and rationale dropped;
`last_mutation` is never persisted; `state.errors` is discarded too. `handleRetry`
([LessonPanel.tsx:199-211](../../../../../frontend/components/LessonPanel.tsx)) then
renders one string for all three, and its comment asserts the *specific*
interpretation — *"no candidate was a smaller foundation than the stop they are
on"* — which is true of only one of them.

**So a generation failure is reported to the learner as a considered judgement.**
For this session, `_has_prerequisite` is `False`, so the cap did not fire; the
reason was `no_useful_prerequisite` **or** `generation_failed` and **nothing
recorded distinguishes them.** The learner clicked three times, which is what
someone does when a button appears not to work.

This is a measurement problem as much as a UX one: [`learning-engine.md`](../../learning-engine.md)
§18.15 records "a learner-requested warm-up no longer depends on the automatic
action" as shipped and validated, but **no evidence in this repository can say how
often that path declines on principle versus fails**, because the distinction is
not stored anywhere. Contrast the `/respond` path, which does carry
`declined_reason` in the attempt envelope.

**F53 — [FACT] The round produced its first `verified` gap.** Stop 8's gap
`710552d6…` is now `status: verified`, `resolved_by: 1`, closed by a real
verification answer. M3b recorded **0 verified, 0 waived, 0 verification attempts
across every database that exists**; this is the first, and it exercised M6's
`verify` → `grade_verification` path end to end on a real session.

Two observations from it:

- **`verification_attempts: 0` on a verified gap is correct, not a bug.** Only
  `record_failed_verification` increments ([gaps.py:217](../../../../../backend/learning/gaps.py));
  `mark_verified` does not, and `gap_insight` compensates by defining the tested
  population as `verification_attempts > 0 **or** status == "verified"`
  ([gap_insight.py:171](../../../../../backend/learning/gap_insight.py)). Checked
  because it looks wrong at a glance. *(Low-confidence aside: `"retried"` counts
  `verification_attempts > 1`, so a gap that failed once and then verified is not
  counted as retried — worth a look when M3b's thresholds are calibrated.)*
- **Passing verification promoted nothing visible.** The node's stored assessment
  is still `partial` (the latest *assessment* was `partial`; verification is not
  an assessment), so `understanding_of` returns `partial`. Per design — but it is
  F38's theme a third time: the learner demonstrated the corrected model and no
  surface reports a change.

### Lesson 8 — "Extract information from a returned Node" (stop 9)

| | |
|---|---|
| node | `55ae4a31af7a425181ab0c6054437822` |
| anchors | **`Node` 68–130** · `Node.solution` 105–107 · `Node.path` 109–115 |
| outcome | answered once, `understood` |

**Reviewer verdict:** one of the stronger lessons — good placement, objective,
anchors and question; the `solution()`/`path()` distinction deserves its own unit.
One wording fix: *"The Node holds … a chain of parent nodes back to the start"*
should say each Node holds a **parent reference**, and those references form the
chain `path()` walks.

**F54 — [FACT] This is the round's third positive control, and the sharpest,
because it is the same class stop 7 got wrong.**

| | stop 7 *Call astar_search* | stop 9 *Extract information from a returned Node* |
|---|---|---|
| `Node` anchors | `Node.solution` **105–107** only | **`Node` 68–130** (the whole class, `child_node` 99–103 included) |
| claim about `Node` construction | *"`GraphProblem.result()` … becomes the action recorded in the child Node"* — **false** (F45) | *"`depth` … incremented in `__init__` as `parent.depth + 1`"*, *"`path_cost` accumulates via `child_node`"* — **both exact** |

Verified against source: `self.depth = parent.depth + 1` (search.py:86),
`path_cost` set in `child_node` (101-102), `path()` walking `node.parent` and
reversing (109-115). Every one of those lines is inside `Node` 68–130 and outside
`Node.solution` 105–107. **Same class, same session, two units, opposite
outcomes — and the discriminator is anchor coverage again**, replicating F27 on a
different symbol. Two independent replications now support the thesis; nothing in
the round contradicts it.

**The wording point is confirmed and is intra-lesson, not a factual error.**
`Node.__init__` does `self.parent = parent` (search.py:81) — a single reference,
exactly as the reviewer says. The `setup` says "a chain of parent nodes"; the
`reveal` says *"`path()` walks the parent chain backward from the goal node to the
root, then reverses it"*, which is precise and correct. So the imprecision is in
the framing text and the mechanism is right where it matters — the same
setup-loose / body-exact split seen in lesson 1 (F2, F7), but harmless here
because nothing false is asserted.

**Two small opportunities, recorded not as defects:**

- The reviewer's suggestion to say *why* `path()` returns Nodes — so the caller can
  inspect `state`, `action`, `path_cost`, `depth` at every step — is exactly what
  the objective already promises ("describe a debugging workflow using `path()`")
  and the reveal only gestures at ("debug intermediate states or costs").
- The reveal illustrates with a hypothetical `[Node(Arad), Node(Sibiu),
  Node(Bucharest)]`, while the real Romania path — `['Sibiu', 'Rimnicu',
  'Pitesti', 'Bucharest']` — is in `tests/test_search.py:79` and was anchored two
  stops earlier. Using the real one costs nothing and would ground the trace.

#### Lesson 8, second pass — the takeaway contradicts the reveal on the unit's own distinction

**Reviewer verdict:** verdict correct, feedback strong, and — unlike the earlier
remediation text — it does **not** keep correcting misconceptions that are no
longer present (F36's failure mode absent here, because no re-teach fired). One
precision issue, on the central distinction.

**F55 — [FACT] Confirmed, and both of the reviewer's quotes are the same
sentence pair.** Stop 9's stored `takeaway`:

> *"A Node stores both the goal state and **the chain of decisions** that reached
> it. `solution()` returns the action sequence …, while **`path()` returns the
> state chain** …"*

Its `reveal`, in the same payload:

> *"**`path()`** walks the parent chain backward … It returns a list of
> **Nodes**"*

`path()` returns `list(reversed(path_back))` where `path_back` accumulates `node`
objects (search.py:109-115) — the reveal is right. The takeaway replaces the
lesson's own `Node`-vs-state distinction with a plausible but wrong dichotomy
("action sequence vs state chain"), and it does so **in the field designed to be
the retained summary.** As the reviewer notes, it also destroys the reason `path()`
is useful for debugging at all: what a Node carries beyond `state` — `action`,
`path_cost`, `depth`, `parent`. (`ownership` is fine: *"the mechanics of how they
walk the parent chain are safe to delegate"*.)

**This is the fifth internal contradiction of the round, and the pattern is now
worth naming.**

| # | where | contradiction |
|---|---|---|
| F2 | lesson 1 | `setup`'s "two must / two may override / one default" vs its own `reveal` |
| F7 | lesson 1 | `takeaway` groups `h` under "silently changes behaviour" vs `reveal` "`h()` raises" |
| F33 | warm-up | title about `h` vs objective about `path_cost` |
| F51 | grading | rationale credits "cost vs. hop optimality" while opening a gap saying it was conflated |
| **F55** | lesson 8 | `reveal` "list of Nodes" vs `takeaway` "state chain" |

Five instances across eight lessons, one warm-up and one grading call. **Three of
the five are in the `takeaway`** — the field that compresses, and compression is
where the distinction gets dropped.

**[REC] This is the cheapest check the round has surfaced, and the only one that
needs no repository access.** Every other candidate (F21/F44's anchor coverage,
F45's data-flow claims) requires resolving symbols against source. Detecting a
`reveal`/`takeaway`/`setup` contradiction is a self-consistency pass over **one
JSON payload** — no anchors, no skeleton, no dossier, and it would have caught
F2, F7, F33 and F55 without knowing anything about the repository. It is also the
only check that would work unchanged on a repository in a language the system
cannot parse, which makes it relevant to
[`multi-language.md`](../../multi-language.md) as well.

### Lesson 9 — "Trace the A* runtime flow end-to-end" (stop 10)

| | |
|---|---|
| node | `37810367a57f4295b78bc56645b863a6` |
| anchors | `astar_search` 415–420 · **`best_first_graph_search` 260–287** · **`Node.expand` 94–97** · **`Node.child_node` 99–103** |
| prompt kind | `predict-next` |
| outcome | not yet answered |

**Reviewer verdict:** very well placed, strong objective, well-chosen anchor
chain. Two cautions: the expected answer must test the semantic flow rather than
"it's the next statement", and the title promises an end-to-end trace while the
question tests one transition.

**The first caution does not materialise.** The stored `expected_answer` is
substantive, not syntactic — it names `expand` → `problem.actions` →
`child_node` → `problem.result()` / `problem.path_cost()`, then the
explored/frontier checks, then the loop returning to pop the next node. That is
the flow the reviewer asked for.

**F56 — [FACT] The second caution is real, and it interacts badly with how
grading works.** The objective demands the **whole** trace ("naming which Problem
methods are called and when"); the prompt asks about **one** transition after
`explored.add(node.state)`. Because the Grader marks against the objective —
`LEARNING OBJECTIVE (the marking standard)`, with the question supplied only as
context (F23) — the two possible outcomes are both wrong in different directions:

- the Grader marks against the broad objective, and a learner who answers *exactly
  what was asked* is marked short for omitting the rest of the trace;
- or it marks the narrow question, and the objective's breadth is never assessed.

This is the same shape as the warm-up case (F31/F32), where passing the exercise
gave no evidence about the misconceptions that triggered it. **Assessment coverage
of the objective is now a two-instance pattern**, and it is distinct from every
anchor finding in this round: nothing about grounding is wrong here, and no source
would help.

**Two things this unit does better than anything before it.**

1. **Its anchor set is complete.** Every symbol the objective names is anchored,
   including `best_first_graph_search` and `child_node` — the two whose absence
   caused F20, F22, F29, F40 and F45. This is the unit F44 identified as the
   journey's first anchoring of `best_first_graph_search`, arriving four claims
   too late. The pattern across the journey is now legible: **units that are
   *about* a mechanism anchor it correctly; earlier units that merely *reference*
   it do not.**
2. **[FACT] `learning-engine.md` §14 item 11 is met, verified live.** The
   criterion is *"`prompt_kind` is chosen from `kind` and takes at least four
   distinct values across a single real journey."* Across the ten lessons rendered
   so far: **4 distinct values**, and the mapping from `kind` is consistent —

   | unit kind | prompt_kind | count |
   |---|---|---|
   | `component` | `predict-then-reveal` | 5 |
   | `extension_point` | `locate` | 1 |
   | `flow` | `predict-next` | 2 |
   | `architecture` | `compare` | 1 |
   | (warm-up, no `kind`) | `predict-then-reveal` | 1 |

   B4's form selection works as designed. `risk` units (stops 13, 16) map to the
   AI-critique form per §7.4 and have not been rendered yet, so a fifth value may
   still appear. **This is the first live verification of that criterion recorded
   anywhere in the project.**

#### Lesson 9, second pass — the takeaway contradicts itself one clause later

**Reviewer verdict:** verdict and runtime trace good; the takeaway's *"ensures you
visit the cheapest nodes first"* is wrong for A\*, which pops lowest `f = g + h`,
not lowest `g`; and *"only generate children when you're ready"* is vague.

**F57 — [FACT] Both halves of the contradiction are in the same sentence pair.**
Stop 10's stored `takeaway`:

> *"…pop the **lowest-f-score** node from the frontier… The order—pop, goal-test,
> then expand—ensures you visit the **cheapest nodes first**…"*

It states the rule correctly and then paraphrases it wrongly, one clause later.
The `reveal` is right (*"evaluate each child (via the memoized `f`)"*), and the
source is **anchored and unambiguous**: `frontier = PriorityQueue('min', f)`
(search.py:270), `node = frontier.pop()` (search.py:273).

**This is the important qualification to the round's central thesis.** Every
earlier correctness failure was outside the anchors (F20, F22, F29, F40, F45) and
every fully-anchored claim was right (F41, F43, F54). Here the unit's anchor set is
**complete** (F56) and the reveal is correct — yet the takeaway is wrong. So:
**anchor coverage governs whether the model can know the mechanism; it does not
govern whether the summary preserves it.** The two failure modes are independent,
and a fix for one will not touch the other.

**`takeaway` error tally: 3 of the 9 rendered lessons** — F7 (lesson 1, `h`
grouped with silently-defaulting methods), F55 (lesson 8, `path()` "returns the
state chain"), F57 (here). In every case the same payload's `reveal` is correct.
F55's recommendation is strengthened rather than merely repeated: this instance
needs no cross-field comparison at all — **one field contradicts itself**, so the
cheapest possible check would still catch it.

**And the A\*/UCS conflation recurs for the fifth time.** "Cheapest first" is a
correct description of `uniform_cost_search`, whose `f` **is** `node.path_cost`
(search.py:292) — the model has re-imported UCS semantics into A\* exactly as it
did in F20, F22, F29 and F40. **Anchoring changed the severity, not the presence:**
in the unanchored units this produced false mechanism claims; in this anchored one
it produced a loose paraphrase beside the correct statement. It is the single most
persistent error of the journey, and no check proposed so far — anchor coverage,
self-consistency, prerequisite closure — would have caught all five instances.

**On "only generate children when you're ready":** vague, and slightly worse than
vague — it implies a choice the code does not have. `best_first_graph_search`
expands unconditionally once `goal_test` fails; there is no readiness condition.

### Lesson 10 — "Understand the heuristic contract for A*" (stop 11)

| | |
|---|---|
| node | `5670b29cc65f4855bf33cd2dab69ef69` |
| anchors | `astar_search` 415–420 · `GraphProblem.h` 1206–1215 · `utils.distance` 376–380 |
| outcome | answered once → `partial` |

**Reviewer verdict:** right topic, placement and anchors, but the lesson teaches
**admissibility** as the *single* property guaranteeing `astar_search` finds the
cheapest path. Given the explored-set behaviour traced in the previous unit,
**consistency/monotonicity** is the condition this implementation actually needs.

**F58 — [FACT] The reviewer is right, and it is the eighth instance of the anchor
pattern.** What the lesson asserts:

> `reveal`: *"The critical constraint is **admissibility**… If your heuristic
> overestimates … A\* may prune the optimal path"*
> `takeaway`: *"if it violates admissibility, A\* will silently produce suboptimal
> paths"*

Why that is not sufficient **for this code**, verified line by line:

- `best_first_graph_search` does `explored.add(node.state)` and then admits a child only `if child.state not in explored and child not in frontier` (search.py:274-277) — a state already expanded is **discarded, never reopened**;
- membership is **by state**, not by node: `Node.__eq__` is `self.state == other.state` (search.py:122-123) and `__hash__` hashes the state.

So this is graph search without re-expansion, where an admissible-but-inconsistent
`h` can pop a state along a costlier path first, close it, and then silently
discard the cheaper path to it. Admissibility alone does **not** preserve
optimality here; consistency (`h(n) ≤ cost(n, n') + h(n')`) is the condition that
does.

**Root cause, and it is the familiar one: `best_first_graph_search` is not
anchored on this unit.** The anchors are `astar_search` (a 6-line delegating
stub), `GraphProblem.h` and `distance` — the extension point and an example, with
**no search loop**. The unit reasons about A\*'s optimality guarantee without the
code that implements the search. What makes this instance notable is that the
source *was* available one stop earlier: stop 10 anchors
`best_first_graph_search` 260–287 (F56) and stop 11 drops it. **Anchors are chosen
per unit with no memory of what the journey has already established.**

**And the unit that would correct it is both later and not required.**
*"Understand explored-set semantics and why graph search differs from tree
search"* is **stop 12**, anchored precisely on `best_first_graph_search` 260–287,
with `priority: recommended`. It is on the walk, but it is **excluded from the
required set** — so the goal is deemed met without it, and a learner can complete
every required objective holding a false optimality guarantee that the journey
itself later contradicts.

**The reviewer's bridge is the right fix and it is free:** introduce consistency
here, motivated by the explored set, and let stop 12 show the mechanism. It
repairs the claim, orders the two units by dependency, and needs one extra anchor
that a neighbouring unit already carries.

**Credit — the API half of the contract is precise.** The reviewer asked that the
expected answer be exact about how `h` is supplied and what it receives; the
`reveal` already says *"pass `h=your_function` … or override `problem.h`"* and
*"`h(node)` receives a Node and must return a numeric estimate of the cost from
that node's state to the goal"* — correct on both the dual supply path and the
Node-not-state argument, and it correctly excludes `g(n)` and total cost.

#### Lesson 10, second pass — the Grader penalised a correction and opened a gap on a true statement

**This is the round's headline finding.** Everything below is verbatim from the
stored attempt.

The learner answered the API half correctly, gave admissibility, and then added:

> *"…additionally, for this graph-search implementation, which does not reopen
> states once they are in `explored`, the heuristic should be **consistent**,
> meaning `h(n) ≤ c(n,n') + h(n')` … Consistency is the stronger condition that
> preserves the optimality guarantee with this closed-set behavior."*

That refinement is **correct for this implementation** (F58). What the system did:

| stage | output |
|---|---|
| classification | `partial`, `gap_kind: right_idea_wrong_altitude` |
| rationale | *"correctly identifies where and how to supply a custom heuristic and grasps admissibility, **but introduces consistency as a required property when the learning objective asks only for admissibility**; this conflates implementation-detail robustness with the core contract"* |
| gap `7fc98e75…` | claim: *"The heuristic must be consistent … in this graph-search implementation that does not reopen explored states"* — **a true statement, recorded as a misconception** |
| follow-up | *"…is admissibility (never overestimating) itself sufficient for optimality, or is consistency required by this specific implementation?"* |

**F59 — [FACT] Conformity to the objective outranks correctness, by
construction.** The rationale states the reason in its own words: the answer was
downgraded *because* it exceeded the objective, not because anything in it was
wrong. This is structural, not incidental:

- the objective is supplied as **`LEARNING OBJECTIVE (the marking standard)`** and the `expected_answer` only as a *"Calibration reference"* (F23);
- **no source reaches the Grader at all** (F23), so there is no channel through which a refinement more correct than the rubric could be recognised;
- therefore an oversimplified objective (F58) is not merely un-correctable — it is *enforced*, and the more a learner knows, the worse they score.

**The follow-up makes it self-refuting.** Having marked the learner down for
introducing consistency, the system generated a remediation question asking
whether consistency is required by this specific implementation — **the exact
question the learner had just answered correctly.** The system is not confused
about the technical content; it is confused about who is right.

**F60 — [FACT] This contradicts two recorded gap-model positions at once.**

1. The M2 prompt addendum **excludes true statements from the gaps list**; a true statement is now recorded as one.
2. `gap-model.md` limitation #3 states `right_idea_wrong_altitude` is *"nearly unreachable as a gap — the addendum excludes true statements from the gaps list, and altitude errors are true at some level"*. It fired here — **on a true statement**, which is precisely the route the limitation assumed was closed. The post-M10 boundary work sharpened `wrong_model` vs `right_idea_wrong_altitude`; it did not consider a claim that is true *and more precise than the objective*.

**Mitigation that did hold:** `right_idea_wrong_altitude` is non-blocking
([graph.py:213-215](../../../../../backend/learning/graph.py)), so this gap does not
withhold `understood`; it renders as *"Worth knowing"* rather than *"Holding this
stop back"*. The damage is to the record, the follow-up and the learner's
confidence — not to progression.

**Session gap census — 5 gaps, and 2 of them record true statements:**

| stop | kind | status | records |
|---|---|---|---|
| 2 | `wrong_model` | open, blocking | **a true claim** (F20) |
| 5 | `wrong_model` ×2 | open, blocking | genuine misconceptions (deliberate wrong answer) |
| 8 | `wrong_model` | **verified** | genuine misconception, correctly closed (F53) |
| 11 | `right_idea_wrong_altitude` | open, non-blocking | **a true claim** (F59) |

Two of five gaps are false positives, arrived at by **two different mechanisms** —
Teaching confabulating past a missing anchor (F20), and the Grader enforcing an
oversimplified objective (F59). The sample is small and skewed (two answers were
deliberately wrong), so the *ratio* means little; the *mechanisms* are what
generalise.

**F61 — the two inaccuracies in the correction, both confirmed.**
*"prune the optimal path"* mis-describes what an inadmissible `h` does — it
reorders the frontier and can cause an early goal-test on a costlier path, which
is not pruning. And *"will silently produce suboptimal paths"* should be *may*:
violating admissibility forfeits the **guarantee**; a particular run may still
return the optimal path. Same modal over-claim as F51's *"UCS … slower than A\*"*.

**[REC] This is the clearest argument in the round for the grade-time source
change (F23), and it needs one addition.** Source at grading time would let the
Grader check a claim against the code. It would not, on its own, tell it what to
do when the learner is right **and** off-objective. That needs an explicit
instruction: *a claim that is true of the repository is never a gap, even when the
objective does not ask for it* — which is the M2 addendum's existing rule, applied
to a case it did not anticipate.

### Lesson 11 — "Understand explored-set semantics" (stop 12, `recommended`)

| | |
|---|---|
| node | `e793f185093e414689f5ca97519560cf` |
| anchor | `best_first_graph_search` 260–287 (complete for its claims) |
| outcome | answered once, `understood` |

**Reviewer verdict:** important topic, correct placement, but *"it only adds child
states to frontier if they haven't been seen before"* collapses three distinct
cases; the "when would you need tree search instead" framing is misleading; and the
link back to lesson 10's admissibility/consistency question should be explicit.

**F62 — [FACT] The `reveal` already does what the reviewer asks; the defect is in
the `setup` and the `prompt`.** The reveal distinguishes all three cases
explicitly — explored ⇒ discarded, in-frontier ⇒ replaced when `f` is better,
neither ⇒ added — and even names the branches. So this is the **fourth** instance
of loose framing over a precise body (F2, F55, F57, and here), and the first where
the loose sentence is what the learner reads *before* answering, which is when it
does the most damage: the `setup` is the framing the question is answered from.

**F63 — [FACT] The prose cites line numbers, and both citations are wrong — a
grounding hole the anchor system does not cover.** Actual source:

| line | code |
|---|---|
| 279 | `explored.add(node.state)` |
| 280 | `for child in node.expand(problem):` |
| **281** | `if child.state not in explored and child not in frontier:` |
| 282 | `frontier.append(child)` |
| **283** | `elif child in frontier:` |
| 284–286 | `if f(child) < frontier[child]: del … ; append …` |

What the reveal says:

- *"**Line 279–280** checks `child.state not in explored`"* — that check is on **281**; 279–280 are the `explored.add` and the `for` header;
- *"**lines 281–283** handle it by checking `child in frontier` and replacing with the better path"* — that is **283–286**, and **281 is the explored check it had just attributed to 279–280**.

CLAUDE.md's guarantee is that *"the model names a `file` + `symbol`; our code
derives the line range, so a hallucinated range is structurally impossible"* —
true of **anchors**, which resolve through `anchors.resolve`. **Line numbers
written into lesson prose bypass that entirely.** A learner following the citation
lands on the wrong lines, and nothing in the system can notice. This is a new
failure class for the round: not missing evidence (F21 family) and not lossy
compression (F57 family), but an **unvalidated grounding claim inside otherwise
correct prose** — and it is mechanically checkable, since a line reference either
matches the cited code or does not.

**F64 — the tree-search framing, and the missing bridge.** The reviewer's
objection is well founded: `expected_answer` says *"use tree search only if the
domain is acyclic or **path history is part of the state**"*, which presents
switching algorithms as the response to path-dependent states. The better lesson
is the reviewer's: if two arrivals at the "same" state have different futures, the
**state representation is wrong** — `(city, fuel)`, not `city` — and that is a
`Problem`-design decision this journey has already taught (stop 3, and stop 13
"Recognise the risk of mutable or unhashable states" is about state identity too).
Tree search is then a genuinely different trade, not a fallback.

**And the bridge to lesson 10 is absent.** Nothing in this unit's `reveal`,
`expected_answer` or `takeaway` connects the closed-state behaviour to the
admissibility-vs-consistency question — even though this unit's single anchor is
exactly the code that makes consistency necessary (F58). The two units are
adjacent, share the decisive source, and neither references the other. Compounding
it: **this unit is `recommended`, not `required`**, so the material that would
repair stop 11's false optimality claim sits outside the required set (F58).

#### Lesson 11, second pass — an error inside a fully anchored unit, and why

**One correction to the framing first:** the answer was graded `understood` with
`response: {"action": "none"}` — **no re-teach fired**. The text reviewed is the
unit's *original* `reveal`, authored **before** the answer existed. So the
reviewer's criterion — post-answer text needs its own grounding — is not merely
right, it is stronger than stated: this text could not have been conditioned on
the answer at all (the F35 mechanism again).

**F65 — [FACT] The frontier-duplicates claim is false, and the reviewer's
reasoning is exactly right.** The reveal says *"If the same state appears in
frontier multiple times with different f-values…"* and *"if the graph has
redundant paths of equal cost, both may be queued before either is popped."*

`PriorityQueue.__contains__` is `any([item == key for _, item in self.heap])`
([utils.py:759-761](../../../../../data/repos/aima-python/utils.py)) and
`Node.__eq__` compares **states** (search.py:122-123). So in
`best_first_graph_search` the first branch is guarded by `child not in frontier`
and the `elif` replaces rather than adds — **a state can appear in the frontier at
most once.** Equal-cost redundant paths do not both queue: the second fails
`f(child) < frontier[child]` and is dropped.

**Why this happened is the interesting part, and it rescues the round's thesis
rather than breaking it.** This unit's single anchor is
`best_first_graph_search` 260–287 — which contains the *operators* (`child not in
frontier`, `frontier[child]`) but **not their semantics**. Whether `in` compares
by identity or by state lives in `PriorityQueue` (utils.py:722-777), which is
**not anchored here**. Read the anchored code alone and "duplicates accumulate" is
a reasonable inference. So the refinement is: **anchoring a function does not
anchor the behaviour of the types it operates on.**

And the corrective unit is late again — *"Understand PriorityQueue as the frontier
mechanism"* is **stop 14**, anchors `PriorityQueue` 722–777 **and**
`best_first_graph_search` 260–287, `priority: recommended`. That is the **third**
instance of this exact structure: `best_first_graph_search` first anchored at stop
10 after four wrong claims (F44); consistency's evidence at stop 12 after stop 11
asserted otherwise (F58); `PriorityQueue`'s semantics at stop 14 after stop 12
mis-described them. **The journey consistently makes claims about a mechanism one
to four stops before it anchors it.**

**F66 — [FACT] The second inaccuracy *is* inside the anchor, and it is an
omission rather than a falsehood.** *"any future encounter with that same state
(via a longer or equal-cost path) will be discarded"* — every word is true, but
the parenthetical implies a better path would **not** be discarded. The anchored
line is `if child.state not in explored and child not in frontier:` (search.py:281)
with **no cost comparison at all**: a cheaper route to a closed state is discarded
exactly like a worse one. As the reviewer says, that omitted case is precisely
what links this unit to lesson 10's consistency question (F58) — and it is the
case the sentence quietly excludes.

So the honest statement of the round's pattern, now that both halves are visible:
**anchored ⇒ the reveal's positive claims have been right in every case; anchored
does not ⇒ the reveal states the whole rule.** F66 is an under-specification
within the anchor; F65 is a false claim about code outside it. Different failures,
different fixes.

**F67 — the tree-search claim is over-categorical, as reported.** *"will loop
infinitely on cyclic graphs"* → *can* revisit states repeatedly and may fail to
terminate. `breadth_first_tree_search` (search.py:178, **unanchored here**) will
still find a reachable goal on a finite cyclic graph; non-termination is the
no-reachable-goal case. Same modal over-claim family as F51 and F61 — and, again,
about code this unit does not anchor.

**[REC] The reviewer's proposed criterion is the right one and belongs in the
phase's quality bar:** *a correct grade is not evidence that the accompanying
explanation is correct.* This round now has both dissociations — grading right /
text wrong (here, and F29/F30), and grading wrong / text wrong (F20) — so the two
must be measured separately or a single "lesson quality" number will average them
into noise (first argued at F30, now with a third instance).

### Lesson 13 — "Understand PriorityQueue as the frontier mechanism" (stop 14, `recommended`)

**First, the numbering gap the reviewer noticed is a real skip.** Stop 13
*"Recognise the risk of mutable or unhashable states"* — **`priority: required`**
— has `cached=Y`, `visited=0`, `attempts=0`, `not_started`: its lesson was
rendered and then passed over. Stop 12 has `visited=1`, so `/advance` was used
there; nothing returns to stop 13 (F17). The reviewer's own lesson numbering
(9, 10, 11, **13**) is an accurate self-report of the orphaned stop.

**The text reviewed is a re-teach** (`partial` → `action: reteach`), so the
"comprehension question" critiqued is the **superseded** one, and F36 applies
again: stop 14 now opens permanently with *"What you wrote: reinsertion uses
append to place the new node at the end."*

**F68 — [FACT] The gap records a claim the learner never made. Third false gap of
the round, third distinct mechanism.** The full answer says:

> *"it first **deletes the old frontier entry** and then **appends the new
> child**… the append **inserts the improved path with its lower `f` value**."*

The recorded gap says:

> *"The reinsertion operation uses `frontier.append(child)`, **placing the new
> node at the end of the frontier**."* — `foundational: True`, **blocking**, open

The bolded half appears **nowhere** in the answer. The learner named the method
the code actually calls and described it as *f*-aware insertion — the opposite of
a naive list append. The Grader inferred a misconception from the word "append"
and recorded the inference as the learner's belief.

The three false gaps now have three different causes:

| finding | mechanism | what the gap records |
|---|---|---|
| F20 | Teaching confabulated past a missing anchor; Grader inherited the false `expected_answer` | a true claim |
| F59 | objective oversimplified; correct refinement treated as deviation | a true claim |
| **F68** | Grader **attributed** a belief the learner did not express | a claim never made |

F68 is the most clear-cut of the three: no source is needed to see it, only the
answer text the Grader was already given.

**F69 — [FACT] The reviewer's counterfactual concern is right, and the learner
answered it correctly while the rubric did not.** The superseded `expected_answer`
says that without the re-insertion *"the old, worse-scoring node **would remain in
the frontier** and would pop first … causing the algorithm to expand a suboptimal
path"*. That contradicts its own premise: `del frontier[child]` has already run,
so the old entry does **not** remain. The learner wrote the correct consequence —
*"that state would disappear from the frontier entirely … potentially missing the
optimal solution or even failing to explore a necessary route at all"* — precisely
the reviewer's point, and it was neither credited nor corrected. **Second instance
of a learner being more accurate than the marking standard** (after F59), this time
without penalty for it.

**Also uncredited:** the answer ends with *"a duplicate state already in
`explored` is discarded, while a duplicate state still in the `frontier` can be
replaced"* — exactly the contrast F62/F64 recorded as missing from lesson 11. The
learner supplied it unprompted; the re-teach does not acknowledge it and still
does not state it.

**F70 — [FACT] Line citations use an undeclared, inconsistently accurate
reference frame — F63 extended.** This lesson cites four locations:

| citation | resolves to | correct? |
|---|---|---|
| *"line 27 in the code: `frontier.append(child)`"* | search.py **286** = anchor-relative 27 | ✅ relative |
| *"lines 26–27"* (delete + reinsert) | search.py **285–286** = relative 26–27 | ✅ relative |
| *"`PriorityQueue.append` (**line 14** in utils.py)"* | actual utils.py **738** = relative **17** | ❌ off by 3 |
| *"executes `heapq.heappush(…)` on **line 15**"* | actual utils.py **740** = relative **19** | ❌ off by 4 |

So the frame is **relative to the anchor excerpt** and is never declared — *"line
27 in the code"* reads as absolute — and it is right for one file and wrong for
the other. F63 recorded that prose line references bypass `anchors.resolve`; this
adds that they are not even in a stated coordinate system. Both are mechanically
checkable, and the check is the same one: does the cited location contain the
quoted code, under either frame?

**On the reviewer's substantive points:** the "two operations" framing does omit
the lookup/compare step at search.py:284 (`if f(child) < frontier[child]`), so the
branch is compare → delete → insert, and calling it two operations describes only
the mutations. That is a fair reading of the superseded prompt, and the re-teach
does not fix it — it changes the subject to heap mechanics instead.

#### Lesson 13, second pass — a false claim *inside* the anchor, and the round's clearest split

**F71 — [FACT] The complexity claims are wrong, and the anchored source
contradicts them on the very lines it was given.** `PriorityQueue` **722–777 is
an anchor of this unit**, so every line below was in front of the model:

| operation | implementation | actual cost |
|---|---|---|
| `append` | `heapq.heappush` (utils.py:740) | O(log n) ✓ |
| `pop` | `heapq.heappop` (751) | O(log n) ✓ |
| `__contains__` | `any([item == key for _, item in self.heap])` (761) | **O(n)** |
| `__getitem__` | linear scan (766–768) | **O(n)** |
| `__delitem__` | scan + `.index(True)` + `del` + **`heapq.heapify`** (774–777) | **O(n)** |

What the lesson asserts, in four places:

> `takeaway`: *"deletion + reinsertion … **both are O(log n)**"*
> `expected_answer`: *"…the deletion-and-reinsertion update mechanism **O(log n)** per improvement found … **without the cost of a full frontier scan**"*

The replacement branch actually performs `child not in frontier` (O(n)) →
`frontier[child]` (O(n)) → `del frontier[child]` (O(n) + a full `heapify`) →
`append` (O(log n)). **Three full frontier scans and a re-heapify** — the exact
cost the lesson says is avoided. The learner's instinct to check the claim against
the implementation rather than against generic heap knowledge was correct.

**F71b — the synthesis this forces, and it revises the round's thesis.** Until now
every correctness failure was outside the anchors and every anchored claim held.
F57 (a `takeaway`) and F66 (an omission) were partial exceptions; **F71 is not
partial** — it is a flatly false assertion about anchored code, in the unit whose
whole subject is that code. Sorting all the round's errors by *claim type* rather
than by anchor coverage explains everything:

| claim type | anchored | unanchored |
|---|---|---|
| **mechanism / control flow** — what is called, in what order, what is stored | **reliable**: F41, F43, F54, F56, and this lesson's own correct account of push/pop | **confabulated**: F20, F29, F45, F65 |
| **property / guarantee** — complexity, optimality, termination, "silently", "always" | **still wrong**: F57 (cheapest-first), **F71 (O(log n))** | wrong: F58 (admissibility), F61, F67 |

**Anchoring fixes mechanism claims. It does not touch property claims.** Every
property claim in this journey that went beyond restating the code was wrong,
whether or not the source was in front of the model — because a property is a
*conclusion about* code, and the model reaches for the textbook conclusion rather
than reading the implementation that violates it. This is the same generic-prior
failure as the A\*/UCS conflation (five instances), now visible as a category
rather than a recurring accident.

**Consequence for the fix set:** the two plan-time anchor checks (F21/F28/F44)
address the top row only. The bottom row needs a different intervention — either
verification of property claims against source, or an instruction that complexity,
optimality and termination claims may only be made when the source states them.
**That is a distinct recommendation and it was not visible until this lesson.**

**F72 — [FACT] The grading rule the reviewer states is the right one, and it names
F68's mechanism precisely.** *Absence of an implementation detail must not be
converted into positive evidence of the opposite misconception.* The learner's
answer was correct at the algorithmic level and simply did not say that
`PriorityQueue.append` delegates to `heapq.heappush`. The honest feedback is
*"your replacement logic is correct; you did not explain what
`PriorityQueue.append()` does internally"* — an **omission**. What the system
produced instead was a `foundational`, **blocking** gap asserting a belief
("placing the new node at the end") that appears nowhere in the answer.

Omission and misconception need different handling: an omission is a prompt for
elaboration and should not gate `understood`; a misconception is a gap. The
gap-model's M2 addendum already excludes true statements from the gaps list
(F60); it has no rule excluding **unstated** ones.

#### The warm-up built from the fabricated gap

| | |
|---|---|
| node | `be9608bc267b45489f67b33410708071`, inserted 20:37:34, `origin: learner_request`, unlocks stop 14 |
| title | *"See how PriorityQueue.append uses heapq.heappush to insert by f-value"* |
| display anchor | `utils.py` **`PriorityQueue.append` 738–740** |
| `lesson_brief` keys | `objective`, `why`, `understand`, `priority`, `origin` — **no `remediates`**, **no `anchors`** |

**Reviewer verdict:** well targeted *to the stored gap*, but the stored gap is
unsupported by the learner's evidence — so the chain is *correct method name →
grader infers list semantics → fabricated misconception → warm-up repairs the
fabrication*. Remediation quality must be evaluated end-to-end: **learner evidence
→ gap → warm-up**, and here only the second link is sound.

**F73 — [FACT] The fabricated gap has propagated into a second, durable
artifact.** The warm-up's `setup` states the invented belief as the learner's own:

> *"**Contrast what you might expect**—items go in at the end of a list—with what
> actually happens here."*

That expectation exists nowhere in the answer (F68). It now exists in two places:
the stored gap and a permanent node in the graph. **A fabricated misconception
becomes curriculum.**

**F74 — [FACT] `remediates: None` again — second instance, and it confirms F31's
prediction.** The gap is `wrong_model`, whose policy action is `reteach`, so
`Diagnosis.from_node` designates no gap for a structural mutation and the field is
omitted. Both warm-ups in this session are therefore unlinked to any gap. The M3b
`remediation_closure` template counts warm-ups carrying `remediates`; **this
session produced two warm-ups and zero links**, which is the outcome F31 predicted
from the code. That template is uncomputable in practice for the commonest gap
kind, not merely data-poor.

`anchors: None` and the deprecated `understand` key also recur — F34, unchanged.

**F75 — [FACT] The warm-up contradicts the unit it was built to unlock, and the
contradiction is about code outside its anchor.** Its `reveal` ends:

> *"The heap handles reordering automatically; **you never delete and reinsert**."*

`best_first_graph_search` **does** delete and reinsert — `del frontier[child]`
then `frontier.append(child)` (search.py:285-286) — and that branch is the entire
subject of stop 14, the unit this warm-up precedes. A learner arriving from that
question reads a flat denial of it.

Note precisely where the error falls: the warm-up's anchor is
`PriorityQueue.append` 738–740, and **every claim inside that anchor is correct** —
the `(f(item), item)` tuple, `heapq.heappush`, the min-heap invariant, the root
holding the minimum. The single false statement is about `best_first_graph_search`,
which this unit does **not** anchor. **F71b's top row, reproduced exactly:
anchored mechanism claims right, unanchored mechanism claim wrong.**

**Credit — the risk the reviewer flagged did not materialise.** `heapq.heappush`
maintains the heap invariant, not a globally sorted list, and the lesson says so
correctly throughout: *"heapq maintains heap invariant immediately—the lowest
f-value item is always at index 0"*, and the `expected_answer` says the item
*"remains at the root"*. Nowhere does it claim sorted order. Recorded because the
reviewer raised it as a thing to watch and the artifact passed.

**[REC] The reviewer's evaluation frame should be adopted for the phase.**
Remediation is a three-link chain — **learner evidence → detected gap → generated
warm-up** — and this round now has instances failing at each link independently:
link 1 broken with link 2 sound (here, and F68); link 2 broken with link 1 sound
(F31/F32, where the gap was real but the warm-up tested something else); and both
sound (stop 8's verified gap, F53). Scoring remediation as a single quality
judgement would blur three distinct failure modes with three distinct fixes.

### Lesson 12 — "Recognise the risk of mutable or unhashable states" (stop 13, `required`, `kind: risk`)

| | |
|---|---|
| node | `107e855a3b6844faa0eef13b35ef0d34` |
| anchors | `Node.__hash__` 125–130 · `best_first_graph_search` 260–287 |
| outcome | answered once, `understood` |

**Reviewer verdict:** good objective, but the worked example fails earlier and for
a different reason than intended, and the `Node.__hash__` framing confuses two
contracts.

**F76 — [FACT] The example never reaches the failure it is teaching.** The
constructed problem is `EightPuzzleCustom((1, 2, 3, 4, 5, 6, 7, 8, 0))` — the
initial state is a **tuple**, not a `PuzzleState`. So `Node(problem.initial)`
holds a tuple, `explored.add(tuple)` succeeds (tuples are hashable), and the first
expansion calls `result(state, action)`, whose body is `state.tiles.copy()` →
**`AttributeError: 'tuple' object has no attribute 'tiles'`**. No `PuzzleState` is
ever hashed. The reviewer's correction is right: the initial state must be
`PuzzleState([...])` for the intended failure to occur.

**F77 — [FACT] And the intended failure is described wrongly too — the lesson has
the Python semantics backwards, contradicting its own objective.** The reveal says:

> *"Since `PuzzleState` doesn't define `__hash__`, it **inherits the default object
> hash (based on memory address)** … the explored set never deduplicates … leading
> to infinite loops"*

In Python 3, a class that defines `__eq__` **without** `__hash__` has `__hash__`
set to `None` and its instances are **unhashable**: `explored.add(state)` raises
`TypeError: unhashable type: 'PuzzleState'` immediately. There is no identity-hash
fallback and no silent de-duplication failure. The **objective is correct** — it
says *"predict what breaks (**TypeError** or incorrect deduplication)"* — and the
lesson teaches only the second branch, which is the one that cannot happen here.
So this unit contains **both** an unreachable example (F76) and a wrong account of
the failure it was aiming at.

**This extends F71b's bottom row beyond the repository.** The false claim is about
**Python's data model**, not about `aima-python`. No anchor could have supplied
it, because the evidence is not in the repository at all. The round's two
plan-time anchor checks (F21/F28/F44) cannot reach this class of claim even in
principle.

**F78 — [FACT] The two contracts are inverted, and the correct relation was
inside the anchor.** The setup says *"`Node.__hash__` (which enables **states** to
be stored and looked up in sets and dicts)"*. `Node.__hash__` is
`return hash(self.state)` ([search.py:125-130](../../../../../data/repos/aima-python/search.py),
**anchored**) — it makes **Nodes** hashable *by delegating to the state*, which is
the opposite direction. `explored` stores states directly (`explored.add(node.state)`,
search.py:279), so the state's own hashability is what matters.

Stronger still: **`Node.__hash__` is never exercised by this flow.** `explored` is
a set of *states*; `child not in frontier` goes through
`PriorityQueue.__contains__`, which compares with `==` (utils.py:761); the heap is
a plain list. No `Node` is ever placed in a hash-based structure here. So the
anchor chosen to teach the objective is not the code the objective is about.

**Note on grading:** the answer was graded `understood`. Nothing in the pipeline
can detect that the question's premise is broken — the Grader receives no source
(F23) and nothing executes the example. **A unit can be `required`, `risk`-kind,
built on an unrunnable example and a false mechanism, and still produce a clean
`understood`.**

### Lesson 14 — "Recognise the risk of missing or incomplete graph definitions" (stop 16, `required`, `kind: risk`)

| | |
|---|---|
| node | `7fc0062712a047ae8509b4f252ebd16d` |
| anchors | `GraphProblem.h` 1206–1215 · `GraphProblem.path_cost` 1194–1195 · `Graph.get` 1043–1051 |
| outcome | answered once, `understood` |

**Reviewer verdict:** good risk-oriented lesson; but *"can silently break any of
them"* overstates the blast radius, the question tests only one of the objective's
two failure modes, and the expected answer should not describe `h = np.inf` as A\*
degrading to UCS.

**F79 — [FACT] F22 has arrived, propagated into five fields, with an invented
mechanism attached.** The false claim first recorded at F22 — in this unit's
**objective**, ten lessons before it was taught — is now in the `objective`,
`reveal`, `expected_answer`, `takeaway` and implicitly the `why_now`. And the
reveal supplies a mechanism for it that does not exist:

> *"…when all are infinite, **it falls back to exploring by path cost alone**—this
> degrades A\* to uniform-cost search… **The solution will still be correct
> (uniform-cost is complete)**, but A\*'s heuristic guidance is lost"*

There is no fallback. `PriorityQueue.pop` is `heapq.heappop(self.heap)[1]` over
`(f(item), item)` tuples (utils.py:740, 751); with every `f` equal to `inf`, tuple
comparison falls through to the second element and `Node.__lt__` is
`self.state < node.state` (search.py:91-92). **Expansion order becomes
lexicographic by state**, not by path cost. And because `goal_test` fires on pop,
the first goal popped is returned — so **the "solution will still be correct"
claim is false as well**. The lesson is wrong about the ordering *and* wrong about
the outcome.

Consistent with [F71b](#f71b): every anchored claim here is right — `h`'s
`if locs:` branch, `graph.get(A, B)` returning `None`, `path_cost`'s `or np.inf` —
and the false one is about `best_first_graph_search`, `PriorityQueue` and
`Node.__lt__`, **none of which this unit anchors**.

**The irony is worth recording rather than enjoying:** a `required` `risk` unit
whose subject is *"failures that produce wrong answers, not exceptions"* delivers
a wrong answer with no exception, and the learner was graded `understood` on it.
This is the **sixth** appearance of the A\*/UCS conflation (F20, F22, F29, F40,
F57, F79) and the first where it is the unit's central teaching point.

**F80 — the scope mismatch is real, and it is the third instance of a distinct
pattern.** The objective names **two** silent failure modes; the `takeaway` covers
both; the **question tests only `locations`**. Missing-edge behaviour —
`graph.get(A, B)` → `None` → `path_cost`'s `or np.inf` — is anchored
(`Graph.get` 1043–1051, `GraphProblem.path_cost` 1194–1195) and never assessed.
With the warm-up (F31/F32) and lesson 9 (F56), **assessment coverage of the
objective now has three independent instances**, and it is the one finding family
that no grounding fix touches: the source is present and correct, the objective is
present and correct, and the question simply tests a fraction of it.

**F81 — *"can silently break any of them"* is wrong, as reported.** `why_now`
says the lesson *"shows you the hidden failure modes that can silently break **any
of them** when used with GraphProblem"*, immediately after the learner has been
taught to choose between A\*, BFS and UCS. `breadth_first_graph_search` and
`uniform_cost_search` never call `h` — a missing `locations` dict is invisible to
both. The correct scope is *heuristic search using the built-in `h`*. Same
over-generalisation as F30 (*"GraphProblem works as-is only when your graph has a
`locations` dictionary"*), recurring in a unit whose anchors would have supported
the precise statement.

**[REC]** The reviewer's structural suggestion — either add a missing-edge
scenario or narrow the objective to heuristic metadata — is the right pair of
options and mirrors the F20 fix pair (add the anchor, or move the claim). Note
which is cheaper here: the missing-edge evidence is **already anchored**, so
extending the question costs nothing, while narrowing the objective would discard
correct material.

#### Lesson 14, second pass — a wrong answer graded `understood`, and the round's proof of what grading is measured against

**Reviewer method:** an intentionally wrong answer asserting that missing
`locations` makes A\* behave like uniform-cost search and that *"the missing
`locations` affects performance rather than correctness"*.

**F82 — [FACT] The system graded it `understood`, opened zero gaps, and said why.**

| field | value |
|---|---|
| classification | `understood`, `gap_kind: none`, `graded: True` |
| gaps | **none opened** — the node's gap list is empty |
| response | `{"action": "none"}` |
| rationale | *"The developer correctly identifies both the silent failure mode (h() returns np.inf, causing A\* to degrade to uniform-cost search) and its consequence (no error, but inefficient exploration and correct result), **which is exactly what the objective requires**."* |

The Grader states its own criterion in its last clause. The objective encodes the
falsehood (F22, F79); the objective is supplied as *the marking standard*; **no
source reaches the Grader** (F23). An answer that matches a false objective is
therefore graded correct **by construction** — there is no path by which the
repository could contradict it.

**F82b — this and F59 are exact duals, and together they settle what grading
measures.**

| | learner's claim | vs the objective | vs the repository | verdict |
|---|---|---|---|---|
| **F59** | consistency is required for optimality here | **exceeds** it | **true** | `partial` + gap opened on a true claim |
| **F82** | missing `locations` → UCS, result still correct | **matches** it | **false** | `understood`, zero gaps |

**The ground truth of grading is the objective, not the repository.** Both
directions are now demonstrated on the same repository, in the same session, with
the same Grader. Nothing else in this round establishes the point as cleanly.

**The five grading failure modes observed, for the end-of-round summary:**

| # | finding | failure |
|---|---|---|
| 1 | F20 | gap opened on a **true** claim, from a confabulated `expected_answer` |
| 2 | F49 | **multi-gap miss** — 3 misconceptions in, 1 gap out |
| 3 | F59 | correct refinement **penalised** for exceeding the objective |
| 4 | F68 | misconception **attributed** that the learner never stated |
| 5 | **F82** | **false positive** — a wrong answer graded `understood` |

**F83 — the internal contradiction the reviewer names is the sixth of the
round, and it is inside one unit.** `reveal`: *"The solution will still be correct
(uniform-cost is complete)"*. `takeaway`: *"both failures … **produce wrong
answers, not exceptions**"*. Both cannot be the general conclusion. This one **is**
reachable by the cheap self-consistency check proposed at F55 — which would have
flagged the unit even though nothing could have flagged the grade.

**F84 — the "unreachable node" wording, and a missed opportunity inside the
anchor.** `graph.get(A, B)` returning `None` means the **A→B transition** is
absent; `B` may still be reachable via another path — so *"an unreachable node is
silently treated as an infinite-cost path"* (objective and `takeaway`) conflates a
missing edge with an unreachable node. The imprecision is inherited from the
objective, as in F79.

Worth noting what the unit had in hand and did not use: its own anchor
`Graph.get` 1043–1051 contains `links = self.graph_dict.setdefault(a, {})` — a
**read that mutates the graph**, inserting an empty entry for any unknown node.
That is a genuine silent behaviour, anchored, in a `risk` unit about silent
behaviours, and it goes unmentioned while the unit teaches a fabricated one.

### Lesson 15 — "Synthesise: own a working search integration" (stop 17, `required`, `kind: synthesis`) — final unit

| | |
|---|---|
| node | `58766f8b3318435ba73cc7d6c2c2a820` |
| anchors | `Problem` 15–62 · `GraphProblem` 1179–1215 · `astar_search` 415–420 · `Node.solution` 105–107 |
| outcome | answered once → `partial`, `reteach`; **2 gaps opened** |

**Reviewer verdict:** strong final objective; add algorithm selection explicitly;
replace the "caught by code vs your responsibility" split with noisy / silent /
domain-modelling failures; and — the caution that matters — *"make sure the
synthesis checklist is grounded only in verified repository behavior … not inherit
oversimplifications from earlier lesson text."*

**F85 — [FACT] The same claim received opposite verdicts two stops apart, and the
discriminator is the objective. This is the A/B that proves [F82b](#f82b).**

| | stop 16 (F82) | stop 17 (here) |
|---|---|---|
| learner claim | *"missing `locations` → A\* behaves like UCS … affects performance rather than correctness"* | *"If locations are missing, A\* simply behaves like uniform-cost search and still finds the cheapest route"* |
| verdict | **`understood`**, 0 gaps | **`partial`**, gap opened `wrong_model` |
| rationale | *"…exactly what **the objective** requires"* | *"…**when in fact** missing locations causes a silent heuristic failure … breaks optimality guarantees"* |
| that unit's objective | *"missing locations … making A\* degrade to uniform-cost search"* (F22) | *"ensure locations are populated if using A\*"* |

Same session, same Grader, same repository, minutes apart. **The verdict tracked
the objective in both cases.** The learner was told the claim was correct, then
told it was a misconception, with no acknowledgement that the system had asserted
it first.

**F86 — [FACT] A third fabricated mechanism, and the reveal contradicts both its
own setup and its own grading rationale.** The journey has now explained the
all-`inf` frontier three different ways, none correct:

| unit | claimed mechanism |
|---|---|
| stops 2 / 5 / 16 | *"degrades to uniform-cost search"* |
| stop 16 reveal | *"falls back to exploring by path cost alone"* |
| **stop 17 reveal** | *"the search order **degrades to FIFO-like behavior**"* |

Actual: `heapq` compares `(inf, node)` tuples, ties fall through to `Node.__lt__`
→ `self.state < node.state` — **lexicographic by state** (F79). And the reveal
then concludes *"The path is still optimal (UCS guarantees that)"*, which
contradicts:

- its own `setup`, two paragraphs earlier: *"That answer **might be wrong**, or just slow"* — which is correct;
- the Grader's rationale for this very attempt: *"**breaks optimality guarantees**"*.

So one unit contains the correct statement (setup), the correct grading (rationale)
and the false conclusion (reveal). Seventh internal contradiction of the round —
and the first where the *grading* is right and the *teaching* is wrong within the
same node, the F30 dissociation at its sharpest.

**Anchors again explain the split**: `Problem`, `GraphProblem`, `astar_search`,
`Node.solution` are anchored and every claim about them is right;
`best_first_graph_search`, `PriorityQueue` and `Node.__lt__` are **not anchored**,
and every claim about search ordering is wrong. [F71b](#f71b), fifth confirmation.

**F87 — algorithm selection is named in the objective and never assessed.** The
objective says *"call the right search function"*; the three scenarios are all
A\* + `locations` + a misspelled goal. BFS/UCS/A\* selection — taught as a major
decision point at stop 8 — is not tested anywhere in the synthesis. **Fourth
instance of assessment-coverage-of-the-objective** (F31/F32, F56, F80, here), and
the most consequential, since this is the unit that certifies the whole journey.

**F88 — the final checklist consolidates F58's incomplete contract.** *"verify the
heuristic is admissible"* is exactly the condition F58 showed to be insufficient
for this implementation, which does not reopen closed states. The reviewer's
caution is therefore **validated in the strongest possible place**: the last unit
of the journey hands the learner a checklist containing a known-incomplete
guarantee, and nothing downstream will ever revisit it.

**Credit — the reference style improved.** This unit cites *"(line in anchor 2)"*
and *"lines in anchor 4 show `.solution()` exists"* — **anchor-relative pointers
rather than fabricated absolute line numbers**. That is exactly the form F63 and
F70 found broken elsewhere, and here it is unambiguous and correct.

**The reviewer's proposed taxonomy is better than the lesson's** and is worth
recording as the recommended framing: **noisy runtime failures** (`NotImplementedError`,
`TypeError` from unhashable states) · **silent semantic failures** (inherited unit
`path_cost` in a weighted domain) · **domain-modelling failures** (a state omitting
information that changes future legal actions). The lesson's "caught by the code vs
your responsibility" cuts across all three and puts the two most different failures
— a crash and a wrong answer — on the same side.

#### Lesson 15, second pass — the grading improves, the explanation does not

**Reviewer verdict:** both real errors were caught — the UCS-fallback belief and
the "connected domain means no `None` check" belief. The `None` teaching is
strong. But the re-teach still reconstructs an unsupported fallback, and the
rationale's *"makes A\* perform no better than uninformed search"* is broader than
the evidence supports.

**The `None` half is correct and worth recording as such.** Search exhausting the
frontier returns `None` (search.py:287); chaining `.solution()` on it raises
`AttributeError`; and the distinction the reveal draws — *"'no path exists' (a
domain fact)"* versus *"'search succeeded' (a code fact)"* — is accurate and is
the most useful sentence in the unit. Both anchored, both right.

**F89 — [FACT] The unsupported comparison, and the surface it appears on.** The
Grader's rationale reads: *"…breaks optimality guarantees **and makes A\* perform
no better than uninformed search**"*. The first clause is correct. The second is a
performance comparison with nothing behind it: with `h = inf` the frontier orders
lexicographically by state (`Node.__lt__`, search.py:91-92), which is not BFS's
level order, not DFS's depth order and not UCS's cost order. It could be worse
than any of them, or accidentally better, depending on how the states happen to
sort. The defensible statement is the reviewer's — **the heuristic no longer
provides useful guidance** — and nothing stronger.

What makes this worth a finding rather than a footnote is *where* it appears. The
A\*/UCS family has now been observed on **every generative surface in the system**:

| surface | instance |
|---|---|
| planner objective | F22 — *"making A\* degrade to uniform-cost search"* |
| lesson `setup` | F86 — correct here, wrong at stop 2 |
| lesson `reveal` | F20, F29, F79, F86 — three different fabricated mechanisms |
| lesson `takeaway` | F57 — *"visit the cheapest nodes first"* |
| **Grader rationale** | **F89** — *"no better than uninformed search"* |
| **Grader verdict** | F82 — a wrong answer graded `understood` |
| re-teach | F79, F86 |

**One misconception, seven surfaces, and no surface can check another.** Teaching
cannot see the Grader; the Grader cannot see the source; the planner's objective
is upstream of both and is the marking standard. This is the round's clearest
argument that the fixes must be *structural* — a per-surface correction removes
one row of that table and leaves the mechanism intact.

**Round status: the walk is complete.** All 17 stops (15 planned units + 2
inserted warm-ups) have been rendered; 13 answered. Findings F1–F89 recorded.

#### The verification on stop 17 — the gap was closed by an answer that restates it

**The reviewer's assessment of the *question* is not in dispute** — it isolated
the right distinction (optimal *in this run* vs *guaranteed* optimal). What
happened next is the finding.

**F90 — [FACT] `grade_verification` marked the gap `verified` on an answer that
repeats the misconception verbatim.** The stored verification attempt
(`kind: verification`, 20:47:15):

> *"…A\* effectively **falls back to uniform-cost search** and relies on the
> graph's edge costs. Because the edge costs are correct, the returned shortest
> path is **still guaranteed to be optimal**; the missing locations only affect
> search efficiency, not correctness."*

The gap it was asked to verify:

> *"If locations are missing, A\* simply behaves like uniform-cost search and
> still finds the cheapest route."*

These are the same claim. The grader's verdict: `gaps_resolved: ['8cd5ff59…']`,
with the rationale *"The answer correctly resolves the efficiency vs. optimality
distinction for missing locations"*. **It resolves nothing — it asserts the
guarantee the gap denies.**

**Why this is the round's most serious finding.** `mark_verified` is documented as
*"The ONLY producer of `verified` … No learner action, override or UI path reaches
here, which is what keeps the artifact meaningful"*
([gaps.py:194-200](../../../../../backend/learning/gaps.py)), and gap-model **M6's
AC2** was accepted on a *double dissociation* — an answer still holding the
misconception fails, a corrected one passes. **Here the holding answer passed.**
The corpus now contains a `verified` gap whose closing evidence contradicts it, and
`verified` is the only status that permits `understood` (F26). Nothing downstream
can distinguish this from a real closure.

**Cause, and it needs no new diagnosis:** `_user_content`
([verification.py:109-122](../../../../../backend/agents/grader/verification.py))
sends the objective, the gap claims, the question and the answer — **no source**
(F25). But note this failure did not even require source: the answer and the gap
claim are both in the prompt and are textually near-identical. A comparison the
grader already had everything to make was not made.

**The other half of AC2 did hold.** The second gap — *"Since the warehouse is
connected, there is no need to check for `None`"* — stayed `open`, and the
rationale says why: *"completely avoids discussing None returns"*. **Per-gap
discrimination works for silence and failed for substance**, which is a sharper
result than either "M6 works" or "M6 doesn't".

**Session verification record, now complete:**

| stop | gap | verification outcome | correct? |
|---|---|---|---|
| 8 | BFS shortest-path | `verified` (F53) | ✅ genuine closure |
| 17 | A\* → UCS fallback | `verified` | ❌ **false closure** (F90) |
| 17 | connectivity ⇒ no `None` check | left `open` | ✅ correct |

Two of the three verification outcomes in this session are right. The corpus went
from **0 verified gaps across every database** to **2 — one of which is false.**
M3b's `verification_outcomes` template would count both.

**F91 — [FACT] The verification question is not persisted, so this cannot be
audited from stored state.** `pending_verification` is cleared on grading
([verification.py](../../../../../backend/agents/grader/verification.py)) and the
attempt record stores only `answer`, `rationale`, `kind` and `gaps_resolved`. The
question that was asked is **gone**. For a mechanism whose whole purpose is to be
the trustworthy producer of `verified`, the one artifact needed to review a
closure — what the learner was actually asked — is the one thing not kept.

---

## Journey-level assessment (reviewer, end of walk)

**Verdict: a strong practical AIMA graph-search / A\* path, not yet a balanced
general Search path.** Preserve the integration and runtime depth; fix
prerequisite ordering; broaden algorithm coverage; keep remediation structurally
separate from the canonical curriculum.

**F92 — [FACT] The A\*-centric weighting is measurable, and it is starker than
the lesson titles suggest.** Anchor census over all 18 units:

| symbol | units anchoring it |
|---|---|
| `astar_search` | **5** |
| `best_first_graph_search` | **5** |
| `GraphProblem` (+`.h`, `.actions`, `.path_cost`) | 9 |
| `breadth_first_graph_search` | 2 |
| **`uniform_cost_search`** | **0** |
| `depth_first_graph_search`, `iterative_deepening_search`, `bidirectional_search`, `depth_limited_search`, `greedy_best_first_graph_search`, `breadth_first_tree_search` | **0** |

Of the search algorithms in `search.py`, **exactly two are ever grounded**: A\* and
BFS. UCS is named in two objectives and anchored nowhere (F47). And *"Survey the
other available search algorithms"* — the one unit whose subject is the rest of
the family — anchors only `best_first_graph_search` and
`breadth_first_graph_search`: **it does not anchor a single algorithm it
surveys.** Ninth instance of the F21 pattern, and the one where it is structural
rather than incidental.

**F93 — the two ordering inversions are both confirmed and already recorded.**
*"Write a minimal Problem subclass"* precedes `GraphProblem` (F28); *"Choose
between search algorithms"* (stop 8) requires admissibility, taught at stop 11
(F48). The reviewer's proposed foundation order — `Problem → Graph → GraphProblem
→ custom Problem` — is the single swap F28 identified, and it dissolves F11's
anchor-borrowing at the same time.

**F94 — [FACT] Remediation is not separated from the canonical path.** Both
warm-ups occupy real positions in `path_order()` — **4 and 14**, exactly as the
reviewer read them off the screen — and both carry `anchors: None` and the
deprecated `understand` key (F34). The data to separate them exists:
`lesson_brief["origin"] = "learner_request"` is on the wire and
`progress.detours()` already reports them apart. **What is missing is that the
journey's own ordering treats a generated remediation as a curriculum stop.**
The reviewer's model — *canonical curriculum + learner-specific remediation
branches* — is what the data already supports and the presentation does not.

This matters more given F73: the stop-14 warm-up exists because of a fabricated
gap (F68). **A misconception the learner never held has become a numbered stop in
their curriculum.**

**F95 — [FACT] "Needs work" is not currently clean evidence of learner
difficulty, and this round can enumerate why.** Of the retries and downgrades in
this session:

| stop | extra attempt caused by | finding |
|---|---|---|
| 2 | Teaching confabulated `h`'s fallback; correct answer marked `wrong_model` | F20 |
| 11 | correct consistency refinement penalised for exceeding the objective | F59 |
| 15 | omitted implementation detail converted into a misconception never stated | F68 |
| 16 | wrong answer accepted because it matched a false objective | F82 |
| 17 | gap closed by an answer restating it | F90 |

**Five of the session's grading events were defective, in four different
directions.** Any analytics built on attempt counts — including learning-graph
M3a.2's deterministic pattern templates and M3b's gap-derived ones — would read
these as evidence about the learner. They are evidence about the system.

The reviewer's proposed retry-reason classification is therefore a **prerequisite
for the analytics already shipped**, not a future enhancement:

> learner misunderstanding · ambiguous or defective question · grader false
> negative/positive · incorrect expected model

Without it, [`learning-graph.md`](../../learning-graph.md)'s metric 20
("cross-node repeated difficulty") and M3b's `gap_outcomes` cannot distinguish a
struggling learner from a defective unit — and this session would supply the
latter to both.

**The reviewer's proposed structure, recorded as the recommended target shape:**

```
Foundation          Problem → Graph → GraphProblem → custom Problem
Using search        call search → inspect Node/results → choose algorithm
Core mechanics      expansion → frontier → explored → duplicate handling
Algorithm families  BFS → UCS → best-first/greedy → A* → heuristic contract
Constraints         PriorityQueue → state equality/hashability
Failure modes       bad graph data → bad heuristic setup → no-solution → bad state representation
Synthesis           state → algorithm → heuristic/cost model → execution → result handling
```

Note this ordering also repairs three recorded defects for free: `best_first_graph_search`
would be anchored before anything claims things about it (F44), UCS would be
grounded before it is used as a comparison (F47), and the heuristic contract would
precede algorithm selection (F48).
