# Goal Agent

The Goal Agent is the entry point to the pipeline. It runs a short dialogue with
the user, collects their answers, and produces a structured `GoalOutput` JSON object
that all downstream agents (Code Structure, Mentor) use as their input.

---

## Files

```
backend/agents/goal/
    __init__.py      re-exports the public API
    questions.py     Question dataclass, all question definitions, routing table
    agent.py         GoalSession, GoalOutput, dialogue logic, Haiku synthesis
```

---

## Dialogue flow

Everyone gets 4 core questions, then 1–2 follow-ups depending on their goal type.

| # | Key | Type | Asked to |
|---|-----|------|----------|
| 1 | `familiarity` | options | everyone |
| 2 | `goal_type_raw` | options | everyone |
| 3 | `primary_goal` | free text | everyone |
| 4 | `background` | free text | everyone |
| 5 | `focus_area` | free text | understand_system / understand_component |
| 5 | `contribution_context` | free text | contribute_code |
| 5 | `error_description` | free text | debug_issue |
| 6 | `tried_so_far` | free text | debug_issue only |

Q2 answer is mapped to an internal `goal_type` via `GOAL_TYPE_MAP` in `questions.py`.
That value determines which follow-up questions are appended.

---

## What Claude does

Claude is called **once**, after all questions are answered. `agent.py` formats the
full Q&A into a prompt and sends it to `claude-haiku-4-5`. Claude's job is to read
the natural language answers and produce a clean structured JSON — inferring fields
like `experience_level`, `depth`, and `focus_area` that the user never stated directly.

The response is parsed with `json.loads` and validated through the `GoalOutput`
Pydantic model. If the JSON is malformed or a field has an invalid value, an error
is raised immediately before bad data can reach downstream agents.

---

## GoalOutput schema

```json
{
  "primary_goal": "fix ConnectionError on retries",
  "goal_type": "debug_issue",
  "focus_area": "retry logic and transport adapters",
  "experience_level": "intermediate",
  "depth": "deep",
  "target_repo": "https://github.com/psf/requests",
  "familiarity": "starting fresh",
  "background": "Python, Flask",
  "error_description": "ConnectionError on third retry",
  "tried_so_far": "increasing timeout"
}
```

`goal_type` is one of: `understand_system` · `understand_component` · `contribute_code` · `debug_issue`

`depth` is one of: `overview` · `moderate` · `deep`

Optional fields (`contribution_context`, `error_description`, `tried_so_far`) are
only present when the user's goal type requires them.

---

## API

Two endpoints handle the dialogue over HTTP.

### `POST /goal/start`

Starts a new session.

**Request**
```json
{ "repo_url": "https://github.com/psf/requests" }
```

**Response**
```json
{
  "session_id": "abc-123",
  "question": {
    "text": "How familiar are you with this codebase?",
    "options": ["Starting fresh — never looked at it", "..."]
  }
}
```

### `POST /goal/answer`

Submits one answer and returns the next question, or the final goal when done.

**Request**
```json
{ "session_id": "abc-123", "answer": "Starting fresh — never looked at it" }
```

**Response — mid-dialogue**
```json
{ "done": false, "question": { "text": "What brings you to this repo?", "options": ["..."] } }
```

**Response — dialogue complete**
```json
{ "done": true, "goal": { ...GoalOutput fields... } }
```

The client calls `/goal/answer` repeatedly until `done` is `true`. The session is
deleted from memory once the goal is returned.

---

## Error responses

| Status | Detail | Cause |
|--------|--------|-------|
| 404 | `session_not_found` | `session_id` doesn't exist or session already completed |
| 400 | `invalid_goal_type_option` | Q2 answer is not one of the defined options |
| 500 | `synthesis_failed` | Claude returned malformed JSON |
