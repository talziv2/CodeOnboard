# CodeOnBoard – Project Proposal

## Problem Statement
Onboarding into large open-source codebases is time-consuming and cognitively demanding.  
Documentation is often fragmented, outdated, or overwhelming.

Developers struggle to answer:
- Where should I start?
- Which files matter for my task?
- What do I need to understand before contributing?

---

## Proposed Solution
CodeOnBoard is a task-driven onboarding assistant that transforms repositories into guided learning experiences.

Users specify **what they want to do**, and the system generates a personalized onboarding experience.

The final-goal experience is not a static list of steps but an **interactive, adaptive learning session** — closer to a tutor than to a documentation tour. The system generates an initial learning graph from the user's goal, then mutates that graph during the session based on the user's behavior: what they understood, what confused them, where they asked for more depth, where they asked to skip ahead.

The graph is also the **product centerpiece**: a persistent, repo-anchored map of *the user's evolving understanding* that survives across sessions. Users return to their map, not to a fresh chat. This is the project's X-factor — frontier chat interfaces fundamentally cannot show a user what they personally understand about a specific codebase.

---

## Interactive Learning Graph (Final Vision)

The onboarding experience is structured around three ideas:

### 1. A learning graph that evolves
- An **initial graph** of learning nodes is generated from the user's goal and the prioritized module map.
- The graph **evolves dynamically** during the session: nodes can be added (prerequisites, deeper sub-topics), removed (skipped areas), reordered (architecture-first vs. details-first), or split into finer-grained sub-nodes.
- The session is stateful — visited nodes, demonstrated understanding, weak areas, skipped areas, requested depth level, and learning preferences all persist and inform the next decision.

### 2. Lesson brief ≠ lesson

A learning node has a structured **brief** — title, file, line range, why it matters, what to understand, related concepts. This brief is a *planning artifact*, not the experience shown to the user.

A separate agent expands the brief into the **actual lesson** at delivery time. The same brief can become a high-level tour, a deep walkthrough, a simplified recap, or a prerequisite-first detour — depending on session state.

### 3. Three roles for the learning loop

| Role | Responsibility |
|---|---|
| **Planner Agent** | Owns the learning graph. Generates the initial graph from goal + prioritized module map. Mutates the graph in response to grader output and explicit user signals. Decides WHAT to teach next. |
| **Teaching Agent** | Takes a learning node + session state → produces the actual educational experience: code walkthrough, explanation, examples, architectural context, simplified version, "what to pay attention to," connections to previously seen concepts, active-learning prompts. |
| **Grader Agent** | Evaluates the user's responses to active-learning prompts. Emits classifications (understood / partial / confused / off-topic) that flow back to the Planner. |

### 4. The user's understanding graph (the centerpiece)

The Planner's internal learning graph and the user's understanding graph are the **same object**, surfaced. The agent needs an internal model of what the user has understood to do adaptive routing at all — exposing that model as a first-class, user-visible artifact is what turns the X-factor from theoretical to *felt*.

**What each node carries:**
- **Code anchor** — file + line range (from Code Structure / RAG)
- **Concept tags** — what this node teaches conceptually
- **Understanding state** — `not-yet` / `partial` / `understood` (driven by Grader output)
- **Coverage flag** — visited or not
- **Confidence** — optional user self-report overlay
- **Weak-spot flag** — set when the Grader classified a response as `confused`

**What the graph supports:**
- **Persistence per (user, repo)** — leave for a week, come back to the same graph
- **One derived overlay: readiness gauge** — heuristic `understood_count / goal_relevant_count`; not a rigorous metric, a useful signal
- **User correction** — the user can override the model (mark a node understood / weak / skip) directly on the graph
- **Session resumption** — on return, the system uses the graph to decide where to pick up

**What the graph deliberately is *not*:**
- Not a file-tree with checkmarks (that's coverage, not understanding)
- Not a repo dependency graph (that's prior art, not differentiated)
- Not a multi-user team artifact in v1 (single-user, local — team flows are a later phase if at all)

### Signals the graph reacts to

Explicit, user-driven: *understood*, *partially understood*, *confused*, *wants deeper explanation*, *wants examples*, *wants to skip*, *wants implementation details*, *wants higher-level architecture first*.

Implicit, Grader-derived: *understood / partial / confused / off-topic*, inferred from free-text responses to active-learning prompts.

### How existing agents fit
- **Goal Agent** — unchanged. Produces the structured goal that seeds the initial graph.
- **Code Structure Agent** — unchanged. Produces the module map + RAG store.
- **Prioritization Agent** — unchanged. Narrows the module map handed to the Planner.
- **Documentation Agent** — feeds the Teaching Agent with real docstring/README quotes when expanding a node.
- **Mentor Agent** — *retired*. Its responsibilities split across Planner + Teaching + Grader.

---

## Initial Target Repositories
The project will initially focus on the following open-source repositories:

### FastAPI
- Python web framework
- Large, modular, production-grade
- Ideal for architectural understanding and feature extension

### Requests
- Python HTTP library
- Smaller, focused, and mature
- Suitable for bug fixing and feature exploration

---

## Task-Driven Onboarding
Users begin by stating a task, such as:
- “Add a new API endpoint”
- “Fix a bug”
- “Understand the architecture”
- “Write unit tests”
- “Run the project locally”

The system maps the task to relevant code components and produces a step-by-step onboarding plan.

---

## Multi-Agent Approach
CodeOnBoard uses multiple specialized agents coordinated by an orchestrator:
- Repository ingestion
- Code structure analysis
- Documentation understanding
- Task mapping
- Mentor planning

---

## Expected Contribution
This project explores how LLMs and agent orchestration can:
- Improve onboarding quality
- Reduce learning friction
- Support structured code comprehension

---

## Evaluation Criteria
- Time-to-task-completion
- User clarity and confidence
- Quality of onboarding plans
