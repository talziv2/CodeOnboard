# CodeOnboard — End-to-End Project Summary

## What CodeOnboard is, in one paragraph

CodeOnboard helps a developer learn an unfamiliar codebase. You give it a link to a project on GitHub and tell it what you're trying to achieve ("I want to understand how requests are handled," "I want to fix this bug," "I want to contribute a feature"). The system reads the code, figures out which parts matter for *your* goal, and then walks you through them as an **interactive, adaptive lesson** — one concept at a time, anchored to real lines of real code. It asks you questions, checks whether you understood, and if you get confused it automatically inserts a more basic lesson first to fill the gap. Your progress is saved, so you can leave and come back where you left off.

This is a final-year CS project. The whole backend exists and is tested; the visual interface (the website you'd click through) has not been built yet — today the system is driven over its web API.

---

# PART 1 — What Already Exists Today

## 1. The problem being solved

Joining a new, large codebase is slow and intimidating. Documentation is often missing or outdated, and a README rarely tells you *where to start reading* for the specific thing you care about. People waste days clicking around files trying to build a mental map. CodeOnboard replaces that aimless wandering with a **personalized, ordered learning path** that points you at exact files and line ranges, explains why each one matters, and adapts as it learns what you do and don't understand.

## 2. A plain-language glossary of the key terms

Because the rest of this document uses these words constantly, here's what each one means in this project:

- **LLM (Large Language Model):** an AI system (here, Anthropic's *Claude*) that reads text and writes text. We use it to analyze code, write explanations, and judge answers. The project uses two sizes: **Haiku** (cheap and fast, used for most tasks) and **Sonnet** (smarter and pricier, used sparingly for the most important reasoning).
- **Agent:** a small, self-contained piece of software with one job, which usually does that job by calling the LLM with a carefully written instruction. CodeOnboard is built as a team of cooperating agents (Goal, Code Structure, Prioritization, Mentor, Teaching, Grader), each a specialist.
- **RAG (Retrieval-Augmented Generation):** a technique where, instead of asking the AI to answer from memory, we first **retrieve** the most relevant pieces of the actual code and hand them to the AI so its answer is grounded in real facts. This is how we stop the AI from "making things up" about a codebase it has never seen.
- **Retrieval:** the act of searching the stored code for the chunks most relevant to a question.
- **Chunks:** the code is broken into small, meaningful pieces — one function or one class per chunk — rather than arbitrary blocks of lines. Each chunk remembers where it came from (file, start line, end line, its name and type).
- **Embeddings:** a way of turning a piece of text (a code chunk, or a search query) into a list of numbers that captures its *meaning*. Two things with similar meaning get similar numbers, so the computer can find "code that's about authentication" even if the word "authentication" never appears. This is what makes meaning-based search possible.
- **Learning graph:** the heart of the product. A map of what you need to learn, made of **nodes** connected by **edges**.
- **Node:** one learning step — a single concept tied to a specific spot in the code (e.g. "Understand the Session object, `requests/sessions.py` lines 1–80"). Each node also tracks how well *you* understand it.
- **Edge:** a connection between two nodes that defines order. A "sequence" edge means "learn A, then B." A "prerequisite" edge means "you need to learn this first." A "deeper" edge means "an optional side-trip."
- **Mentor:** the agent that builds the initial learning graph from your goal and the code.
- **Teaching Agent:** the agent that turns one node into an actual lesson you read.
- **Grader:** the agent that reads your free-text answer to a lesson's question and judges whether you understood.
- **Mutator:** the part of the Mentor that *changes* the graph mid-session — most importantly, inserting a prerequisite lesson when you get confused.
- **Session:** one learning journey for one repo + one goal. It has a saved state: which node you're on, what you've understood, what's still pending.
- **Persistence:** saving that session to disk so it survives closing the app — here, in a small database.
- **SQLite / database:** SQLite is a tiny, file-based database (the whole thing is one file, `data/sessions.db`). We use it to store sessions, nodes, and edges. No separate database server needed.
- **Adaptive learning:** the lesson path is not fixed — it reshapes itself based on your answers.
- **Weak spot / confusion detection:** when the Grader decides an answer shows real misunderstanding, the node is flagged as a "weak spot," and that flag *triggers* the adaptive behavior. The weak-spot flag is "sticky": once set, it stays as a record of a rough patch even after you later master the topic.

## 3. The user experience (the journey, as a person experiences it)

1. **You provide a GitHub repo URL.** (For development the team uses `psf/requests`, a small clean library; `fastapi/fastapi` is used to stress-test on a big codebase.)
2. **A short guided interview.** CodeOnboard asks a handful of multiple-choice and free-text questions: how familiar you already are, *why* you're here (use it / contribute / debug / just understand), what specifically you want to be able to do afterward, and what languages/tools you already know. Depending on your answer to "why," it asks 1–2 tailored follow-ups (e.g. for debugging it asks what error you're seeing and what you've already tried).
3. **The system analyzes the repo** (clones it, reads it, indexes it) and **builds your personalized learning graph.**
4. **You step through lessons one at a time.** Each lesson explains a specific piece of the code in plain language, calibrated to your stated experience level, and ends with a "predict-then-reveal" question that asks you to guess what the code does before reading the full explanation.
5. **You answer in your own words.** The system grades your answer.
6. **The path adapts.** If you nailed it, you move on. If you're confused, the system inserts a simpler, more foundational lesson *before* the hard one, teaches that first, then returns you to the original lesson.
7. **You can leave and come back.** Your progress is saved; returning with the same repo and goal resumes you at the right spot without re-doing the expensive analysis.

> Note: steps 4–7 today happen over the system's web API (the kind of thing a developer drives with a tool like Postman, or that a future website would call). The clickable visual interface is the main not-yet-built piece.

## 4. Under the hood — the agents and how they connect

CodeOnboard is a **pipeline of specialist agents** that pass a shared "clipboard" of information between them. That clipboard is a single data object called `OnboardState` — every agent reads from it and writes its results back to it, and the project rule is that agents *never* communicate any other way. This keeps the system predictable.

Here's the end-to-end flow and what each agent contributes.

### Step A — The Goal Agent (turns a conversation into a structured goal)

The Goal Agent runs the opening interview. It collects your answers, then makes **one Haiku call** to distill everything into a clean, structured "goal object" — a small record containing your primary goal, your goal *type* (one of: understand the whole system, understand one component, contribute code, or debug an issue), your focus area, experience level, desired depth, and so on. This goal object becomes the **single source of truth** that steers every later agent. The dialogue itself is temporary and kept in memory; only the finished goal moves forward.

### Step B — The Code Structure Agent (reads and indexes the repo)

This agent does the heavy lifting of "understanding the raw material," and it's where the RAG machinery lives:

- **Cloning:** it downloads a shallow copy of the repo (`git clone --depth 1` — just the latest snapshot, to save time and space).
- **Chunking:** it parses every Python file using **tree-sitter** (a tool that understands code's grammatical structure) and slices the code into meaningful chunks — one per function or class — rather than arbitrary line blocks. Each chunk is tagged with where it came from and a **role**: is this *source* code, a *test*, an *example*, a *doc*, or *tooling*? That role tag matters later, because a guided system tour shouldn't be cluttered with test files, but a debugging session genuinely benefits from tests.
- **Embeddings:** it converts each chunk into the numeric "meaning fingerprint" described above, using a model (`nomic-embed-text`) that **runs locally on the machine** — no API cost, no key needed. These fingerprints are stored in **ChromaDB**, a database built for meaning-based search. The collection is named after the repo and its exact commit, so if you analyze the same version twice, the system **skips re-indexing** and reuses what's there.
- **Module map:** finally it makes **one Haiku call** to produce a high-level "module map" — a short description of each module, its purpose, what it exposes, and what it depends on. Think of it as an auto-generated table of contents for the codebase.

### Step C — The Prioritization Agent (narrows the focus)

Big repos have dozens of modules, most irrelevant to any one goal. This agent makes **one Haiku call** to decide which modules actually matter for *your* goal and drops the rest. It's smart about it: for a broad "understand the whole system" tour it deliberately *keeps* most modules (with a safety floor so it can't over-prune a tour); for a focused goal it prunes aggressively. If anything goes wrong, it safely falls back to "use everything" rather than breaking the pipeline.

### Step D — Retrieval / RAG (assembling the evidence)

Before the Mentor can plan lessons, the system **retrieves** the most relevant code chunks. This is more sophisticated than a single search:

- It picks a **retrieval strategy** based on goal type. A system tour sweeps every module shallowly for breadth; a focused goal does a deeper, multi-layer search.
- For focused goals it can **decompose the query** — a debugging goal becomes separate searches for the goal, the error message, and what you already tried, so each is matched on its own terms instead of being blurred into one long sentence.
- It uses **Reciprocal Rank Fusion (RRF)** to merge results from different searches fairly, so a large pool of results can't drown out a small but important one.
- It applies a **diversity cap** so one giant file can't hog all the slots.

The net effect: the Mentor receives a curated, balanced set of the *most goal-relevant* real code, not a random grab-bag.

### Step E — The Mentor Agent (builds the learning graph)

The Mentor is the **only Sonnet call** in the core pipeline (the smartest model, used once, because building a good curriculum is the hardest reasoning task). It takes your goal, the narrowed module map, and the retrieved chunks, and produces **5–8 learning nodes connected into an ordered chain**. Each node is anchored to a *real* chunk — a specific file and line range copied verbatim from the retrieved code — plus a short "why this matters" and "what to take away."

The Mentor is carefully guarded against the LLM's tendency to invent things:
- A **distinct-anchor check** ensures no two nodes point at the same code; if they do, it shows the model its mistake and asks again.
- A **grounding check** verifies every node's file+lines actually exist in the retrieved chunks; it auto-fixes small path mistakes and, if a node still references code that wasn't retrieved, it asks the model to redo it using only the allowed list.

The result is stored as the **learning graph**. For backward compatibility, the system also flattens the graph into the older "flat list of steps" format — but from the *same single Sonnet call*, so there's no extra cost.

### Step F — The Teaching Agent (turns a node into a lesson)

When you actually visit a node, the Teaching Agent makes **one Haiku call** to write the lesson. It reads the real source code for that node off disk, pulls 1–2 extra "supporting" chunks for cross-reference context (a related caller or import), and notes which earlier nodes you've already understood so it doesn't re-explain them. It produces a markdown **walkthrough** plus a **"predict-then-reveal" question** and a **model answer** (which the Grader will use). Lessons are **cached on the node** — revisiting a node is free and instant, no second AI call.

### Step G — The Grader Agent (evaluates your answer)

When you respond to the lesson's question in your own words, the Grader makes **one cheap Haiku call** to classify your answer as one of: **understood**, **partial**, **confused**, or **off-topic**. It's told to grade the *understanding*, not the wording — a correct idea phrased clumsily still counts as understood. It then records the result on the node:
- *understood* → node marked understood
- *partial* → marked partial
- *confused* → marked "not-yet," which **trips the weak-spot flag**
- *off-topic* (e.g. "I don't know") → leaves your state unchanged, since you didn't actually answer

If grading ever fails technically, it safely defaults to "partial" rather than blocking you.

### Step H — The Mutator (adaptation and confusion handling)

This is where "adaptive" becomes real. When the Grader returns **confused**, the Mutator springs into action:
- It makes **one Sonnet call** to generate a new, *more foundational* lesson node, choosing its anchor from real retrieved candidate chunks (and rejecting any anchor the model tries to invent).
- It **splices that prerequisite in before** the node you struggled with, rerouting the path so you learn the foundation first and then naturally arrive back at the original, harder node.
- A guard allows **at most one prerequisite per node**, so repeated confusion can't stack endless lessons or burn repeated expensive calls.

A second, cheaper mutation — **skip** — is pure logic with no AI call: it marks a node skipped and moves you on. You can also **manually override** your own graph (mark a node understood, mark it weak, or skip it) — these are direct edits with no AI involved, reflecting the philosophy that the graph belongs to *you*.

## 5. Sessions, progress, and persistence

Every learning journey is a **session** tied to a repo and a goal. The session — its nodes, edges, your understanding state per node, weak-spot flags, cached lessons, and which node you're currently on — is **saved to a small SQLite database** (`data/sessions.db`, three tables: sessions, nodes, edges). Saving happens after every meaningful action, so nothing is lost.

Two features build on this:
- **Resume:** if you start a session for a repo+goal you've done before, the system finds the saved session, moves you to a sensible re-entry point (the first unvisited node whose prerequisites you've already understood), and continues — *without* re-running the expensive analysis or paying for the Mentor again. A `force_new` flag lets you start fresh on purpose.
- **Find your sessions:** you can list all past sessions for a given repo.

A **readiness** gauge (how many nodes you've understood out of the total) gives a simple progress signal.

Importantly, the goal interview and the learning session have **different lifecycles**: the interview is throwaway (kept in memory), while the learning graph is durable (kept in the database).

## 6. Orchestration — how the pieces are wired

The initial analysis pipeline (**Code Structure → Prioritization → Mentor**) is built with **LangGraph**, a framework for running a sequence of steps that share state, with conditional branching. Here it's used so that if the repo analysis fails to produce a module map, the pipeline short-circuits cleanly instead of crashing onward. The interactive part of the product (teaching, grading, mutating during a live session) is driven directly by the web API calling the relevant agents in response to your actions.

The whole thing is exposed as a **FastAPI** web service (FastAPI is a popular Python framework for building web APIs). The main endpoints:
- Goal interview: `POST /goal/start`, `POST /goal/answer`
- One-shot path generation (the older flat output): `POST /onboard`
- Interactive session: `POST /session/start`, `GET /session/{id}`, `GET /session/{id}/lesson`, `POST /session/{id}/advance`, `POST /session/{id}/respond`, `POST /session/{id}/override`, and `GET /sessions`

## 7. Technology stack at a glance

- **Python** backend, **FastAPI** for the web API.
- **Claude** LLMs: **Haiku** for most work (interview synthesis, code analysis, prioritization, teaching, grading) and **Sonnet** for the two hardest reasoning tasks (building the initial graph, and generating a prerequisite on confusion).
- **tree-sitter** for structure-aware code chunking.
- **sentence-transformers** with a local **nomic-embed-text** model for embeddings (no API cost).
- **ChromaDB** as the vector store for meaning-based code search.
- **SQLite** (standard library, no server) for session persistence.
- **LangGraph** for pipeline orchestration.
- **GitPython** for cloning repos.
- A large automated **test suite** (200+ tests) covering the agents, retrieval, the graph model, persistence, and the API.

## 8. Key design decisions and the reasoning behind them

- **A team of small agents instead of one big AI prompt.** Each agent is simple, testable, and replaceable. Easier to reason about and debug than a monolith.
- **One shared state object as the only communication channel.** Prevents tangled, hard-to-trace data flow.
- **Cheap model by default, smart model rarely.** Haiku does the bulk; Sonnet is reserved for graph building and confusion-driven prerequisite generation. The target is under ~$0.10 per run.
- **RAG with strict grounding.** Every lesson node must point at code that was actually retrieved. The Mentor even retries when the model strays. This is the difference between a trustworthy tour and a confident-sounding hallucination.
- **Chunk by real code units, not arbitrary line windows.** A function or class is a teachable unit; 50 random lines are not.
- **Index once per commit, reuse forever.** Re-analyzing the same repo version is skipped, saving time and money.
- **The learning graph is also the user's understanding graph.** The same object that plans the curriculum also records what you know — and the design intends for it to become the product's visible centerpiece. This dual role is the project's distinctive idea.
- **Adapt by inserting prerequisites, with guardrails.** Confusion produces a real, grounded, foundational lesson — but capped at one per node so the system stays sane and affordable.
- **Persistence and resume designed to avoid repeating expensive work.** Returning users skip straight back into their session.
- **Graceful degradation everywhere.** Agents append errors to a shared list and never crash the pipeline; a failed grade defaults to "partial," a failed prioritization falls back to "use everything."

---

# PART 2 — What Is Planned for the Future

These are deliberately *not yet built*. They are clearly separated here so the current state isn't overstated.

**Near-term, directly on top of what exists:**
- **The visual interface (the biggest gap).** There is no website/UI yet. The plan is a graph view (likely using `react-flow`) where the learning graph is the central, clickable artifact: node color shows your understanding (grey/yellow/green), outlines mark the current node and weak spots, edge styles distinguish sequence vs. prerequisite vs. deeper, you click a past node to revisit it, right-click to override, and a readiness gauge sits in the corner.
- **More adaptive moves beyond confusion + skip:**
  - **"deeper"** — optional side-trips into a sub-topic (needs a "return to where I was" pointer).
  - **"simpler"** — re-explain the current lesson more gently (a teaching re-render, not a structural change).
  - **reorder / auto-raise-depth** — speculative reshaping as the system learns your pace.
  - A **manual "I'm lost" button** (today confusion is only detected from graded answers).

**Phase 2 items still outstanding:**
- **A Documentation Agent** (planned to enrich analysis; not yet implemented).
- **Support for languages beyond Python** (added one at a time).

**Richer foundations:**
- **Richer code anchors** — today a node points at one contiguous line range; the plan is to support a primary range *plus* supporting references (callers, imports, cross-file flows).
- **Multi-user identity** — currently single, anonymous, repo-scoped use; adding real user accounts is deferred until needed.
- **Repo URL normalization** — so slightly different forms of the same URL match for resume.

**Later phases (explicitly future):**
- **Phase 4:** TTS audio narration of lessons, and an automated code-walkthrough video.
- **Phase 5 (stretch):** a VS Code extension.
- **Strategic framing for Phase 3+:** position CodeOnboard as a complement to AI code generation — training humans to *understand, critique, and direct* AI-written code, with the Grader's scope expanding toward evaluating critique and reasoning, not just comprehension.

**Out of scope for now:** team-shared graphs, cross-repo dependency overlays, exportable progress reports, and login/cloud sync.

---

### Summary in one breath

Today CodeOnboard is a **complete, working, tested backend**: it interviews you, clones and indexes a repo with structure-aware chunking and local embeddings, retrieves the right code for your goal, has a Mentor build a grounded learning graph, a Teaching Agent write lessons, a Grader judge your answers, and a Mutator adapt the path by inserting prerequisites when you're confused — all persisted in SQLite with resume. The principal thing left to build is the **visual graph interface** that would turn this powerful engine into a polished, clickable product, along with the deeper adaptive moves and the later audio/video/extension phases.
