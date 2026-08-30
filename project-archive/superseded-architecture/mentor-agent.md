# Mentor Agent

The Mentor Agent is the third and final step in the Phase 1 pipeline. Given a
`GoalOutput`, a `module_map`, and an embedded ChromaDB collection, it produces
an ordered 5–8 step learning path that walks the user through the codebase.

This is the only agent in Phase 1 that uses `claude-sonnet-4-6`, and it is
called exactly once per run.

---

## Files

```
backend/agents/mentor/
    __init__.py      re-exports the public API (run, MentorOutput, LearningPathStep)
    agent.py         run(), retrieval helpers, prompt builders, output validation
```

---

## What it does

1. **Branch on goal type** — `state.goal["goal_type"]` selects both the
   retrieval strategy and the prompt builder. There are four goal types:
   `understand_system` · `understand_component` · `contribute_code` · `debug_issue`.
2. **Retrieve chunks from ChromaDB** — see *Retrieval strategy* below.
3. **Drop redundant class chunks** — `_drop_redundant_class_chunks` removes any
   class chunk if one of its methods is also in the same result set. Keeps the
   narrower anchor.
4. **Build the user prompt** — a goal-type-specific builder formats the goal,
   module map, and retrieved chunks into a single user message.
5. **Call Sonnet once** — the system prompt enforces the schema and the rules
   (distinct anchors, narrowest chunk, no invented files, no inferred
   relationships).
6. **Validate and (if needed) retry** — see *Distinct-anchor enforcement* below.
7. **Write** — `state.learning_path` and `state.confidence` are populated.

---

## Retrieval strategy

Two different strategies, selected by `goal_type`:

### `understand_system` — per-module sweep

A tour goal needs breadth, not semantic clustering around one phrase. For each
entry in `state.module_map`, the agent runs a separate ChromaDB query built
from that module's `purpose` and `exports`:

```
"<purpose>. Exports: <exports>"
```

`PER_MODULE_TOP_K = 2` chunks are pulled per module, deduplicated by
`(file, start_line, end_line)`, and capped at `TOP_K = 20` total. This
guarantees chunks span the major modules even if some happen to be far apart
in embedding space.

### The other three — focused query

`understand_component`, `contribute_code`, and `debug_issue` use a single
ChromaDB query enriched with the goal's optional fields:

| `goal_type` | Query composition |
|---|---|
| `understand_component` | `<primary_goal>. Focus area: <focus_area>` |
| `contribute_code` | `<primary_goal>. Contribution: <contribution_context>` |
| `debug_issue` | `<primary_goal>. Error: <error_description>. Tried: <tried_so_far>` |

Missing optional fields fall back to `primary_goal` alone (no crash). Single
embedding, single query, `TOP_K = 20` chunks returned.

---

## Redundant-class-chunk filter

The chunker emits both whole-class chunks **and** per-method chunks. When the
top-K result contains both a class and one of its methods, the class chunk is
redundant — its content covers the method but at a coarser line range, which
pushes the LLM to anchor steps on the whole class instead of the specific
method.

`_drop_redundant_class_chunks(chunks)` solves this. A chunk `cls` is dropped
when a function chunk `fn` exists in the same result set such that:

- `cls["type"] == "class"`, `fn["type"] == "function"`
- same file
- `cls.start_line <= fn.start_line` and `fn.end_line <= cls.end_line`

The class chunk stays in ChromaDB — only the per-query result is filtered.

---

## Distinct-anchor enforcement

The system prompt instructs the LLM that each step must anchor on a distinct
`(file, line_range)` pair. The LLM sometimes ignores this rule. The agent
defends against that with a two-stage check:

1. `_find_duplicate_anchors(output)` scans the parsed `MentorOutput` and
   returns the list of duplicates (empty if none).
2. If duplicates are present, `_retry_distinct_anchors` makes **one** extra
   Sonnet call with the original user message, the LLM's bad output, and a
   correction prompt that names the offending chunks explicitly:

   > Your previous response reused these (file, line_range) anchors across
   > multiple steps: …. Regenerate the JSON object with distinct (file,
   > line_range) pairs for every step.

3. If the retry produces a clean output, it replaces the original. If the
   retry still has duplicates (or fails to parse), the original output is
   kept and a warning is appended to `state.errors`:

   ```
   mentor_agent: duplicate anchors persisted after retry: ['<file>:<start>-<end>', ...]
   ```

At most one extra Sonnet call is ever made, and only when duplicates actually
occur. Clean runs are unaffected.

---

## What Claude does

The system prompt is fixed (`_SYSTEM_PROMPT` in `agent.py`). The user message
varies by goal type — same shared context (goal + module map + retrieved
chunks) plus a goal-type-specific guidance paragraph:

| `goal_type` | Guidance paragraph |
|---|---|
| `understand_system` | "Favour breadth over depth — touch entry points, not internals." |
| `understand_component` | "Go deep into the focus area. Prefer fewer files at greater depth." |
| `contribute_code` | "Order steps so the user understands extension points first, then the file(s) most likely to need editing." |
| `debug_issue` | "Trace the execution path that produces this error. Each step should narrow the search." |

Sonnet's job is to pick 5–8 retrieved chunks (each a distinct
`(file, line_range)`) and produce an ordered narrative around them.

---

## Output schema

```python
class LearningPathStep(BaseModel):
    step: int                    # 1-indexed
    title: str                   # short imperative title
    file: str                    # must come from a retrieved chunk
    line_range: tuple[int, int]  # [start_line, end_line]
    why: str                     # one sentence — why this step matters
    understand: str              # one sentence — what the user should take away
    concepts: list[str]          # ≤ 4 short concept tags


class MentorOutput(BaseModel):
    steps: list[LearningPathStep]
    confidence: Literal["high", "medium", "low"]
```

Sonnet self-rates `confidence` based on how well the retrieved chunks cover
the user's goal:

| Value | Meaning |
|---|---|
| `high` | retrieved chunks clearly cover the goal; the path is concrete |
| `medium` | chunks partially cover the goal; some steps required interpolation |
| `low` | chunks barely related to the goal; mostly guessing |

---

## Entry point

```python
from backend.agents.mentor import run

state = run(state, client=anthropic.Anthropic())
# state.learning_path  → [ { step, title, file, line_range, why, understand, concepts }, ... ]
# state.confidence     → "high" | "medium" | "low"
# state.errors         → [] on success; ["mentor_agent: ..."] on failure
```

`client` defaults to `None` — when omitted, the agent constructs one using
`ANTHROPIC_API_KEY` from the environment.

The agent assumes the upstream Code Structure Agent has populated:

- `state.goal` — validated `GoalOutput` dict
- `state.module_map` — `{ module_name: ModuleEntry }` dict
- `state.chunks_embedded == True`

If any of these is missing, the agent appends an error to `state.errors` and
returns without calling Sonnet.

---

## Error handling

| Error prefix | Cause | Effect |
|---|---|---|
| `mentor_agent: goal missing` | `state.goal is None` | Return early |
| `mentor_agent: module_map missing` | `state.module_map is None` | Return early |
| `mentor_agent: chunks not embedded` | `state.chunks_embedded != True` | Return early |
| `mentor_agent: unknown goal_type <...>` | `goal_type` not one of the four | Return early; no Sonnet call |
| `mentor_agent retrieval failed: <...>` | ChromaDB / embedder failure | Return early; no Sonnet call |
| `mentor_agent LLM call failed: <...>` | API error, malformed JSON, or Pydantic validation failure | `state.learning_path` left as `None` |
| `mentor_agent: duplicate anchors persisted after retry: [...]` | Retry mechanism couldn't fix duplicate `(file, line_range)` step anchors | Original output is kept; warning logged |

---

## Constants

| Name | Value | Meaning |
|---|---|---|
| `MODEL` | `claude-sonnet-4-6` | Only place Sonnet is called in Phase 1 |
| `MAX_TOKENS` | `4096` | Per-call output limit |
| `TOP_K` | `20` | Total chunks passed to the LLM after retrieval |
| `PER_MODULE_TOP_K` | `2` | Chunks pulled per module during the `understand_system` sweep |
