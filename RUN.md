# Running CodeOnboard locally

Everything you need to go from a fresh clone to a running application. For what
the project *is*, see [README.md](README.md).

CodeOnboard runs entirely on your machine: a Python API on port 8000, a Next.js
UI on port 3000, and one SQLite file. Nothing is hosted and nothing phones home
except the Anthropic API, and the `git clone` of whichever public repository you
ask it to teach you.

---

## 1. Prerequisites

| | Version | Check with |
|---|---|---|
| Python | 3.11+ | `python --version` |
| [uv](https://docs.astral.sh/uv/) | any recent | `uv --version` |
| Node.js | 18.18+ | `node --version` |
| git | any | `git --version` |

`git` has to be on your `PATH`: the backend shells out to it to clone the
repository you want to learn.

You also need an **Anthropic API key** from
[console.anthropic.com](https://console.anthropic.com/), with a little credit on
it. See [§7](#7-what-it-costs).

---

## 2. Setup

```bash
git clone https://github.com/talziv2/CodeOnboard.git
cd CodeOnboard
uv sync
cp .env.example .env
```

Then install the frontend's dependencies:

```bash
cd frontend
npm install
cd ..
```

---

## 3. Configure

Open `.env` and paste your key:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Leave `CODEONBOARD_COOKIE_SECURE=0` as it comes. It is already set in
`.env.example`, and it is what lets you stay signed in over `http://localhost` —
the default is `1` (https-only cookies), which is right for a deployment and
wrong here.

Everything else in `.env.example` is commented out and optional. You do not need
a GitHub token, a Google client, or a secret key to run this.

---

## 4. The database

**There is no database step.** On first use the app creates `data/sessions.db`
itself, with an empty schema. Nothing is seeded and no migration is needed.

To reset an installation to brand new: stop both servers, delete
`data/sessions.db`, and start again.

---

## 5. Run it

Two terminals, both from the repository root.

**Terminal 1 — backend:**

```bash
uv run uvicorn backend.api:app --reload
```

**Terminal 2 — frontend:**

```bash
cd frontend && npm run dev
```

Then open **<http://localhost:3000>**.

That is the only URL you need. The frontend proxies `/api/*` through to the
backend, so port 8000 is there for `curl` and for the API docs at
<http://localhost:8000/docs> — the browser never calls it directly.

---

## 6. Check that it works

1. `curl http://localhost:8000/health` → `{"status":"ok"}`
2. Open <http://localhost:3000>. You should land on **Sign in**.
3. Create an account. Any email address works — nothing is sent and nothing is
   verified; the address is just how the app recognises you next time.
4. You land on the dashboard, and it tells you that you have no sessions yet.
   **An empty dashboard with no error on it is the success signal.**
5. Click **Start a new session** and paste a public GitHub repository —
   `https://github.com/psf/requests` is a good first one — then answer the short
   interview about what you want to understand.

Step 5 is where the app first calls Claude and first clones a repository.
Planning runs in the background and takes a few minutes; the card shows
`generating` while it works, and you can close the tab and come back.

---

## 7. What it costs

You are using your own API key, so this is worth knowing before you click.
Planning a session targets **under $0.10**. Lessons and grading use Haiku; the
one Sonnet call is the planner.

---

## 8. If something goes wrong

| What you see | Why | Fix |
|---|---|---|
| Backend exits with `Refusing to start: ANTHROPIC_API_KEY is not set` | no `.env`, or the key line is still empty | `cp .env.example .env` and paste your key |
| `sh: next: command not found` | frontend dependencies not installed | `cd frontend && npm install` |
| The UI loads but every action fails | the backend is not running, or is on a different port | start it; if it is not on 8000, set `API_ORIGIN` in `.env` |
| You sign in and are immediately signed out | `CODEONBOARD_COOKIE_SECURE` is `1` over http | set it to `0` in `.env` |
| `Port 3000 is in use` | something else has it | `npm run dev -- --port 3100` |
| "That repository doesn't exist, or it's private" | only public `github.com` repositories are accepted | use a public GitHub URL |
| No **Sign in with Google** button | Google is not configured | expected, and fine — email sign-in is the normal path |

---

## 9. Running the tests

```bash
uv run pytest tests/
```

```bash
cd frontend && npm test
```

On a fresh clone both suites are green, with seven backend tests skipped. Those
seven read `data/sessions.db`, which does not exist until you run the app.

**Once you have used the app**, one of them —
`test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state`
— starts running and **fails** with `assert 0 > 0`. It is a development gate that
re-checks stored sessions against the current model, and it predates user
accounts: it looks sessions up under a fixed test user, so the ones belonging to
your real account are invisible to it and it concludes there was nothing to
check. It is a known issue in that gate, not a problem with your installation.

To run everything else:

```bash
uv run pytest tests/ --deselect "tests/test_gap_understanding.py::test_every_stored_gap_free_node_derives_its_stored_state"
```

---

## 10. Windows shortcut

`run-dev.bat` opens both servers in their own windows. It is a convenience, not
the supported path — if anything looks wrong, fall back to the two commands in
[§5](#5-run-it).
