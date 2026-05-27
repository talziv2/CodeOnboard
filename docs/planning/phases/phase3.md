# Phase 3 — Interactive Learning Graph

The static 5–8 step path becomes an **interactive, adaptive learning session**. The Mentor Agent retires; its work splits across **Planner**, **Teaching**, and **Grader**. The Planner's learning graph is also the **user's understanding graph** — persisted per (user, repo) and surfaced as the product's centerpiece UI artifact.

Vision detail and rationale live in [`roadmap.md`](roadmap.md#phase-3--interactive-learning-graph). This doc is the build plan.

**Done when:**
- User can run a session that streams one lesson at a time, sends signals (got it / deeper / confused / skip), and the next lesson is conditioned on those signals.
- Free-text responses are graded and the classification influences the next lesson.
- The graph demonstrably mutates during a session on at least one target repo (`psf/requests`).
- The user's understanding graph persists across sessions: closing the app and returning loads the same graph in the same state, with a sensible resume point.
- The graph is visible to the user as the central UI artifact — not hidden inside the agent.

**Scope warning.** Phase 3 is roughly 3–4× the size of Phase 1. Three new agents, a stateful session model, a persistence layer, and a non-trivial graph UI. The build order below front-loads a **thinnest vertical slice** so there's a working end-to-end loop early, then layers mutation / persistence / polish on top. Resist the urge to perfect any one part before the slice runs.

---

## Build order

```mermaid
graph TB
    P1["Part 1 — Graph schema + persistence<br/>LearningGraph dataclass · SQLite store · session model"]
    P2["Part 2 — Planner Agent (static)<br/>goal + map + RAG → initial graph"]
    P3["Part 3 — Teaching Agent<br/>node → lesson (walkthrough + active prompt)"]
    P4["Part 4 — Vertical slice API + UI<br/>one lesson at a time · 'understood / next' only"]
    P5["Part 5 — Grader Agent<br/>classify free-text response → signal"]
    P6["Part 6 — Graph mutations<br/>Planner reacts to signals · add prerequisites · reorder · split"]
    P7["Part 7 — Persistence + resume<br/>session save/load · resume point heuristic"]
    P8["Part 8 — Graph UI<br/>visible centerpiece artifact · click-to-jump · understanding overlay"]

    P1 --> P2 --> P3 --> P4 --> P5 --> P6 --> P7 --> P8

    style P1 fill:#f5f5f5,stroke:#9e9e9e
    style P2 fill:#f5f5f5,stroke:#9e9e9e
    style P3 fill:#f5f5f5,stroke:#9e9e9e
    style P4 fill:#f5f5f5,stroke:#9e9e9e
    style P5 fill:#f5f5f5,stroke:#9e9e9e
    style P6 fill:#f5f5f5,stroke:#9e9e9e
    style P7 fill:#f5f5f5,stroke:#9e9e9e
    style P8 fill:#f5f5f5,stroke:#9e9e9e
```

> Parts 1–4 are the **vertical slice**: by the end of Part 4 a user can step through a fixed graph one lesson at a time. Parts 5–8 turn it into the adaptive product.

---

### Part 1 — Graph schema + persistence ✓ (done)

Skeleton data model + persistence for future steps. No agent code yet; no user flow yet.

**`backend/learning/graph.py`** ✅ — pure dataclasses, no LLM, no IO.
- `LearningNode`: `id` (auto-generated uuid4 hex), `title`, `code_anchor: CodeAnchor`, `concept_tags`, `lesson_brief`, `understanding_state` (`"not-yet" | "partial" | "understood"`), `visited`, `weak_spot` (sticky once set), `user_override`, `cached_lesson`.
- `LearningGraph`: `session_id` (auto-generated), `repo_url`, `goal`, `nodes`, `edges`, `current_node_id`.
- Edge kinds: `sequence` / `prerequisite` / `deeper`.
- Mutation style: in-place (matches `OnboardState`). Methods: `add_node`, `add_edge`, `set_current`, `mark_visited`, `mark_understanding`, `override`, `insert_before` (reroutes sequence edges), `insert_after` (hangs a deeper detour without disturbing sequence).
- Derived: `readiness()` → `understood / total`.

**`backend/learning/store.py`** ✅ — SQLite persistence.
- `data/sessions.db`, three tables: `sessions`, `nodes`, `edges` (with `ON DELETE CASCADE`).
- `save_graph(graph)` / `load_graph(session_id)` / `list_sessions_for_repo(repo_url)` / `delete_session(session_id)`.
- Schema versioning: `schema_version` column; mismatched versions return `None` (no migration logic).
- Millisecond-precision timestamps (`strftime('%Y-%m-%d %H:%M:%f', 'now')`) so session ordering by `updated_at` is stable.

**`OnboardState`** ✅ — added `graph: LearningGraph | None` and `current_lesson: dict | None`. `errors` reducer intact.

**Tests** ✅ — 32 tests across `tests/test_learning_graph.py` (mutation behaviour, readiness math, edge rerouting) and `tests/test_learning_store.py` (save/reload roundtrip, mutation persistence, schema-version mismatch, ordering, cascade delete, cached-lesson roundtrip).

**Deliberately deferred — to revisit when needed:**
- **User identity / multi-user.** Single anonymous user for now. When Part 7 (resume) or Phase 5 (extension) actually needs multiple users, add a `user_id` column + index and a parameter to `list_sessions_for_repo`.
- **Repo URL normalization.** Stored as-is. When Part 7 needs to match `GitHub.com/x/y.git` to `github.com/x/y` for resume lookups, add `normalize_repo_url` at the store boundary.
- **Identity helpers module.** Skipped a separate `ids.py`; UUID generation lives inline in `graph.py` as `_new_id()`. If identity grows beyond UUIDs (user IDs, repo fingerprints, anchor signatures) it can be promoted to its own module then.

---

### Part 2 — Planner Agent (static, no mutation yet)

Generates the **initial** graph from `goal + module_map + relevant_modules + RAG`. Equivalent in scope to the Phase 1 Mentor Agent — same inputs, but the output is a graph object instead of a flat step list.

**`backend/agents/planner/agent.py`**
- Reuses the retrieval logic from Mentor (RetrievalProfile, query decomposition, role filtering, redundant-class drop). Lift it into `backend/rag/retrieval.py` rather than copy-pasting — Mentor and Planner both need it.
- One Sonnet call. Prompt asks for nodes + edges with `kind="sequence"` covering the goal. 6–10 nodes typical (room above the Phase 1 cap of 8 because the graph can also encode prerequisites later).
- Output validated through a `PlannerOutput` Pydantic model that mirrors the `LearningGraph` shape (minus session-state fields, which the agent fills with defaults).
- No mutation logic yet — that lands in Part 6.

**Note on model choice.** Phase 1's rule was "Sonnet only in Mentor, once per run." Phase 3 has three new agents, two of which run in loops. The single-Sonnet rule must be revised:
- **Planner** — Sonnet, called once at session start, and again on each mutation event (rare-ish). Risk: cost.
- **Teaching** — Haiku per lesson (called in a loop). Risk: quality.
- **Grader** — Haiku per user response (called in a loop). Risk: low — classification is easy.

See the **Open design decisions** section for the budget rethink — this is a real decision that affects cost.

**Test:**
- On `psf/requests` with an `understand_component` goal, planner emits a coherent graph; manually inspect nodes anchor on real files and edges form a sensible sequence.
- Token cost on initial-graph generation alone is under $0.05.

---

### Part 3 — Teaching Agent

Expands a single node's lesson brief into the **actual lesson**: walkthrough, examples, architectural context, "what to pay attention to," and **one active-learning prompt** at the end.

**`backend/agents/teaching/agent.py`**
- Input: `node`, `graph` (for prior-context awareness — which nodes are already understood), `goal`, RAG handle.
- Pulls the actual source for the node's `code_anchor` from disk (not RAG — we already know the file/lines), plus 1–2 supporting chunks from RAG for cross-references.
- One Haiku call. System prompt: "you're tutoring a developer at experience-level X, the user already understands these nodes, this node's lesson brief is Y, the source code is Z. Output: walkthrough markdown + one active-learning prompt + prompt_kind."
- Output validated through `LessonOutput` Pydantic model: `walkthrough: str (markdown)`, `prompt: str`, `prompt_kind: "predict-then-reveal" | "free-text-recall" | "find-this"` (pick one form for v1 — see Open decisions).

**Test:**
- On a known node from the `requests` graph, generate a lesson. Manually verify: walkthrough references the real code, the prompt is answerable from the walkthrough, no hallucinated file paths.
- Same node, different `goal.experience_level` → lesson tone shifts.

---

### Part 4 — Vertical slice API + UI

**This is the integration gate.** By the end of Part 4 you can run an end-to-end session with no mutation, no grading, no persistence — just *one lesson at a time, click "next."* If this doesn't feel right, fix it here before adding adaptivity.

**API (additions to `backend/api.py`):**
- `POST /session/start` — body: `{ repo_url, goal }` → runs Code Structure + Prioritization + Planner. Returns `{ session_id, graph }`.
- `GET /session/{id}/lesson` — runs Teaching on `graph.current_node`. Returns `{ lesson, node_id }`.
- `POST /session/{id}/advance` — body: `{ signal: "next" }`. Marks current node visited, advances `current_node_id` along the sequence, returns next lesson or `{ done: true }`.

**UI (additions to `frontend/`):**
- New `/session/[id]` page. Left pane: lesson markdown. Right pane: a *list* view of the graph (a real graph view comes in Part 8). Current node highlighted; previously visited nodes greyed.
- One button: **Got it, next**. Calls `/advance` with `signal: "next"`.

**Done when:** A run on `psf/requests` walks the user through 6–10 lessons, in order, click by click, with no errors.

---

### Part 5 — Grader Agent

Classifies **free-text** user responses to active-learning prompts.

**`backend/agents/grader/agent.py`**
- Input: `prompt`, `expected_answer` (Teaching can produce this alongside the lesson — add to `LessonOutput`), `user_response`.
- One Haiku call. Classification only: `"understood" | "partial" | "confused" | "off-topic"`. Plus a one-sentence rationale (for debugging, not shown to user in v1).
- Pydantic-validated, with a fallback to `"partial"` on parse failure (graceful — never blocks).

**API addition:**
- `POST /session/{id}/respond` — body: `{ response: str }`. Calls Grader, updates the current node's `understanding_state`, sets `weak_spot=True` if confused. Does **not** mutate the graph yet — that's Part 6. Returns `{ classification, rationale }`.

**UI addition:**
- Lesson page gets a free-text input + Submit button below the active prompt. After submit, show the classification and reveal "Continue" → calls `/advance`.

**Test:**
- Synthesize 10 (prompt, expected, response) triples by hand — 3 obviously understood, 3 obviously confused, 4 ambiguous. Grader matches your judgment on the first 6 and gives sane partial/confused calls on the rest.

---

### Part 6 — Graph mutations

Planner stops being one-shot. On each signal, it decides whether to mutate.

**Signals that can trigger mutation:**
- Explicit user actions: *deeper*, *simpler*, *skip*, *go to architecture first*.
- Grader-derived: `confused` → consider inserting a prerequisite node; `understood` repeatedly → consider raising depth.

**`backend/agents/planner/mutator.py`** (separate from initial-graph generator):
- Input: `graph`, `signal`, optionally `current_node`.
- Decides one of: `no-op` / `insert_prerequisite(before=node_id, new_node=...)` / `insert_deeper(after=node_id, new_node=...)` / `reorder(...)` / `skip(node_id)`.
- One Sonnet call **only when the signal is ambiguous or requires generating a new node**. Cheap signals (`skip`, explicit `next`) bypass the LLM and mutate via pure-Python rules.
- Returns a mutated `LearningGraph`.

**API additions:**
- Extend `/advance` to accept signals beyond `next`: `deeper`, `simpler`, `skip`, `confused`.
- Add `POST /session/{id}/override` for direct user-driven graph edits (mark understood, mark weak, drop node).

**UI additions:**
- Lesson page: row of signal buttons (deeper / simpler / skip / "I'm lost").
- New nodes inserted by the mutator visibly appear in the right-pane list.

**Test:**
- Trigger `confused` on a node that has an obvious prerequisite (e.g. ask about adapters before sessions). Mutator inserts the prerequisite node before the current one. Run the session forward — prerequisite is taught first, then the original.

---

### Part 7 — Persistence + resume

The vertical slice already writes to SQLite at session start. Now wire up **load and resume**.

- `POST /session/start` checks if a graph already exists for `(user_id="local", repo_url, goal.primary_goal)`. If so, returns the existing one with `resumed: true`.
- Save the graph on every state change (cheap — SQLite, single-row write).
- Resume point heuristic: prefer the first unvisited node that has all its prerequisites understood; fall back to `current_node_id` from the saved graph.
- UI: on a repeat visit to the same repo + goal, show "Resume from Step N" vs "Start over."

**Test:**
- Run a session through 3 lessons, kill the server, restart, hit `/session/start` with the same repo + goal → resumes at lesson 4.

---

### Part 8 — Graph UI (the centerpiece)

The graph stops being a list and becomes the **central visible artifact**.

- Pick a JS graph library — `react-flow` is the leading candidate (good DX, controllable layout, custom node React components). See Open decisions.
- Visual encoding:
  - Node color = `understanding_state` (grey / yellow / green).
  - Outline = `current_node` (thick blue) / `weak_spot` (red).
  - Edge style = `sequence` (solid) / `prerequisite` (dashed) / `deeper` (dotted).
- Interactions:
  - Click a visited node → jump back to that lesson.
  - Right-click → user override menu (mark understood / mark weak / skip).
  - Top-right: readiness gauge.
- Layout: top-down DAG layout, computed once per mutation (don't animate — the cognitive load isn't worth it for v1).

**Test:**
- Walk a full session on `psf/requests`. Graph reflects state at every step. Clicking a past node loads its lesson without breaking forward state.

---

## Open design decisions

These were deferred in the roadmap. **Lock each one before it blocks its part.**

| # | Decision | Default for now | Blocks |
|---|---|---|---|
| 1 | Active-learning prompt form for v1 | `predict-then-reveal` (lowest grading complexity) | Part 3 |
| 2 | Mentor → Planner: keep Sonnet for initial graph? | Yes, once per session. Mutator uses Haiku when possible, Sonnet only when generating new node content | Part 2 |
| 3 | Persistence: SQLite vs JSON files | SQLite — queries by `(user_id, repo)` are awkward in JSON, and we'll want them in Phase 5 | Part 1 |
| 4 | Identity model | Anonymous local-only (`user_id="local"`). Schema has the column for later. | Part 1 |
| 5 | Graph UI library | `react-flow` (React-native, good docs, custom nodes) | Part 8 |
| 6 | Mutator: rule-based vs LLM-driven | Hybrid. Cheap signals (`skip`, `next`) → pure Python. Signals that need new content (`deeper`, `confused`-needs-prerequisite) → Sonnet | Part 6 |
| 7 | Lesson regeneration on revisit | Cache the rendered lesson on first generation; regenerate only on user request (`/lesson?refresh=true`) | Part 4 |

Anything else uncovered during build that needs a call: append here with a default, don't block the part.

---

## Token budget (rough — Phase 3 changes the rules)

| Agent | Model | When | Est. per session |
|---|---|---|---|
| Goal Agent | Haiku | 1× at start | ~$0.0004 |
| Code Structure Agent | Haiku | 1× at start | ~$0.002 |
| Prioritization Agent | Haiku | 1× at start | ~$0.001 |
| Planner (initial) | Sonnet | 1× at start | ~$0.07 |
| Teaching | Haiku | per lesson, 6–10× | ~$0.03 |
| Grader | Haiku | per response, 6–10× | ~$0.01 |
| Planner (mutator) | Sonnet | ~2× per session (avg) | ~$0.04 |
| **Total** | | | **~$0.15/session** |

**This breaks the Phase 1 $0.10 budget.** Two mitigations to evaluate during Part 6:
- Cache Planner mutator decisions for common signal patterns (`confused` on the same node twice → same prerequisite).
- Try Haiku for the mutator entirely; only fall back to Sonnet when Haiku's output fails validation.

Document the realized per-session cost in the recap once Parts 1–4 are running.

---

## Out of scope for Phase 3

- Multi-user / team-shared graphs.
- Repo dependency overlays (cross-repo learning).
- Exportable progress reports.
- Login / cloud sync.
- TTS narration on lessons (Phase 4).
- Video walkthroughs (Phase 4).
- VS Code extension (Phase 5).
- New language support beyond Python (Phase 2 task, not blocking Phase 3 if we stay on `psf/requests` for development).
