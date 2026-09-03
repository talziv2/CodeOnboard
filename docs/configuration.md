# Configuration reference

> Every environment variable the system reads, what it does, and what happens
> when it is wrong.
>
> Index: [docs/README.md](README.md) · Setup: [root README](../README.md)

Configuration lives in **two** places, and they are read by two different
processes:

| File | Read by | Loaded how |
|---|---|---|
| `.env` at the repository root | the **backend** (Python) | `load_dotenv()` in `backend/api.py` |
| the frontend's own environment | the **Next.js server** | `process.env`, at request time for `API_ORIGIN` |

Copy `.env.example` to `.env` and fill in the one required value. Everything else
in that file is commented out and optional.

## `.env` fills gaps; it does not win

`backend/api.py` calls plain `load_dotenv()`, so the **real environment takes
precedence over the file**. This was `load_dotenv(override=True)`, which inverted
the precedence every other tool in the stack uses: a variable set where the
process was launched was silently discarded, so

```bash
CODEONBOARD_TUTOR=0 uv run uvicorn backend.api:app --reload
```

ran with the Tutor **on** if `.env` said `1` — the opposite of what the person
typing it asked for, with nothing on screen to say so.

Default precedence is what makes both usable for what each is for: the file for
values that never change on this machine, the environment for the ones being
varied right now.

---

## 1. Required

### `ANTHROPIC_API_KEY`

Your own key from <https://console.anthropic.com/>, with a little credit on it.

Every lesson, grade and plan needs it, so the backend **refuses to start**
without one rather than failing later on the first request that reaches a model.

---

## 2. Required for a local `http` run

### `CODEONBOARD_COOKIE_SECURE` — default `1`

Whether the session cookie carries `Secure`, which makes it https-only.
`.env.example` ships `0`, which is what a `http://localhost` run wants.

**The default is on, and that direction is deliberate**: a missing flag in
production means a session cookie sent in clear, so a wrong default should fail
visibly on plain http rather than silently over the internet. (Chromium-family
browsers do accept `Secure` cookies on `localhost`, so a run that forgets this may
still appear to work in one browser and not another — set it to `0` and be sure.)

In production, `0` is a **refusal to start**.

---

## 3. Behaviour flags

**One of them**, and it defaults **on**.

`tests/conftest.py` neutralises it for every test — *neutralised* meaning
**unset**, so it falls to its shipped default rather than to off. A test that
depends on a flag has to say which and how.

### `CODEONBOARD_TUTOR` — default `1`

**The one flag here that is on unless you turn it off**, and it is read
`!= "0"` rather than `== "1"`: unset, `1`, and any unrecognised value all enable
it; only a literal `0` disables. A typo should not silently remove a feature.

`1` serves five routes under `/session/{id}/tutor` — the conversational assistant
in the same pane the source uses. `0` makes every one of them answer **404**
rather than 403 or 501, because "withheld by this deployment" is a fact about our
configuration that no caller needs.

**It has a build-time twin that must be set to match** —
`NEXT_PUBLIC_CODEONBOARD_TUTOR` in §7. Two variables rather than one because they
are read in different processes at different times: this one gates behaviour per
request, that one gates whether the CHAT control is compiled into the bundle at
all. Setting only this one to `0` leaves a control on screen that fails on every
turn.

**The flag gates behaviour; it never gates storage.** Nothing in
`backend/learning/store.py` reads it, so a conversation written flag-on survives a
flag-off load and a flag-off re-save, and returns intact when the flag returns. A
test asserts that structurally.

*Why the default moved.* It was `0` on measured evidence rather than caution:
`docs/planning/phases/evidence/tutor/` records **1 answer leak in 30** adversarial
SCAFFOLD prompts against a stated gate of **0**, and `tutor.md` T8 made a green
Eval 1 the condition for defaulting on. **That gate has not been met.** The
default was changed by decision, so that a fresh clone plus `run-dev.bat` starts
the complete product instead of a feature nobody could reach without finding two
undocumented variables. The architecture still removes the cheap leak — a
`ScaffoldContext` has no field that can hold the answer — so the residual is a
model reasoning its way to the answer from source it legitimately holds, bounded
by the hint ladder's terminus rather than eliminated. Set both halves to `0` for
any run where that matters.

---

## 4. Networking

### `CODEONBOARD_ALLOWED_ORIGINS` — default `http://localhost:3000,http://127.0.0.1:3000`

The CORS origin allow-list, comma-separated.

`localhost` and `127.0.0.1` are the same machine but different **origins** to a
browser, so both are listed: opening the app on the one that is not allowed makes
every call fail CORS, which the browser reports only as "Failed to fetch".

It is needed only for **direct** access to `:8000`. The Next `/api/*` rewrite makes
the app's own requests first-party, so CORS is not load-bearing for them — but
`curl`, Swagger and the smoke scripts all talk to `:8000` directly. Never `*`
alongside credentials; browsers reject that combination, and the explicit list is
what makes it safe.

In production, a value still containing a localhost origin is a **refusal to
start**.

### `CODEONBOARD_TRUST_PROXY` — unset by default

Honour `X-Forwarded-For` when deciding which IP to rate-limit. Leave unset unless
a reverse proxy actually sets it — a header the client controls is otherwise a
throttle bypass, since an attacker would simply vary it.

---

## 5. Google sign-in — entirely optional

Unset means the button is hidden and `GET /auth/google/start` redirects to
`/login?error=google_not_configured`. The feature is **absent** rather than
half-working.

| Variable | Notes |
|---|---|
| `GOOGLE_CLIENT_ID` | Register `http://localhost:8000/auth/google/callback` as the redirect URI for local development |
| `GOOGLE_CLIENT_SECRET` | Set both or neither — half-configured is a refusal to start in production |
| `CODEONBOARD_SECRET_KEY` | Signs the short-lived cookie carrying `state` and `nonce` across the redirect. Without it a per-process random value is used, so flows do not survive a restart. **Required in production**; optional locally so a feature most runs never touch does not block development |

---

## 6. Production

### `CODEONBOARD_ENV` — default `development`

Setting it to `production` turns four checks from silence into a **refusal to
serve**: insecure cookies, a missing signing key, a leftover localhost origin, and
half-configured Google. Every one of those works perfectly until it matters, which
is exactly why a log line is not enough.

It also switches `POST /auth/forgot` from returning the reset link to returning
nothing.

The project is **self-hosted and local-first**; this switch exists so that a
deployment fails loudly rather than quietly, not because a deployment path ships.

---

## 7. Frontend

| Variable | Default | What it does |
|---|---|---|
| `API_ORIGIN` | `http://localhost:8000` | Where `/api/*` is proxied to, read by the **Next server** at request time. It replaced `NEXT_PUBLIC_API_URL`, which was baked into the browser bundle at build time — this one never reaches the client, so the API's address stops being public |
| `NEXT_PUBLIC_CODEONBOARD_UI` | `surfaces` | The lesson renderer. `surfaces` = `Lesson · Understanding` plus the `Map · Analysis` mode; `next` = the earlier single phase-driven canvas, kept as the measurement baseline |
| `NEXT_PUBLIC_CODEONBOARD_TUTOR` | `1` (on) | Whether the Tutor's CHAT control is **compiled into the bundle**. Read `!== "0"`, so only a literal `0` removes it. Must match `CODEONBOARD_TUTOR` in §3. Next inlines `NEXT_PUBLIC_*` at build time, so changing this needs a restart of `npm run dev` — setting it in a running shell does nothing, which is the trap it is worth knowing about |
| `NEXT_DIST_DIR` | `.next` | Where the build cache lives. Two dev servers on this repo at once share `.next` and quietly corrupt each other's view of it — one served a chunk built from the other's environment, and another kept serving a stale chunk for minutes after the source had changed. Neither failure announces itself |

---

## 8. Development-only

| Variable | Used by | Purpose |
|---|---|---|
| `CODEONBOARD_UX_DB` | `scripts/ux_fixture_app.py` | Serve a throwaway fixture database instead of the real one, for walking the UI without spending money. Defaults to `data/ux-fixture.db` |

---

## 9. Not configuration

Worth stating, because their absence is sometimes mistaken for a missing setting:

- **No `GITHUB_TOKEN`.** Cloning is anonymous `git clone --depth 1` over https
  against public repositories only.
- **No database URL.** The path is `data/sessions.db`, a module constant. There is
  exactly one database in production, and an environment variable that can point
  the app at a different one is a way to lose a learner's work.
- **No model configuration.** Model ids are constants in each agent, because which
  model does which job is an architectural decision.
- **No port configuration for the backend** beyond uvicorn's own `--port`.

### Two variables that used to be here

`CODEONBOARD_CURRICULUM` and `CODEONBOARD_GAPS` were removed. **An `.env` that
still sets them is not an error and not a warning — the values are simply
ignored**, which is the one thing worth knowing here, because a stale `.env` line
reads like a setting that is doing something.

Both were migration flags, default `0`, each keeping a superseded implementation
reachable while its replacement was measured:

| Was | `1` selected | `0` selected |
|---|---|---|
| `CODEONBOARD_CURRICULUM` | the objective-first planner, `mentor/curriculum.py` | the pre-B3 node planner, `mentor/dossier.py` |
| `CODEONBOARD_GAPS` | gap recording, and `gap_kind` derived from the gaps found | the scalar `gap_kind` alone, no gaps recorded |

Both replacements won, so both are now simply how the system works — and the
code each flag switched *away* from was deleted rather than left in the tree
where nothing could reach it. `mentor/dossier.py` still exists, holding the
dossier rendering both planners always shared; the planner half is gone.

What did **not** change is the rule those flags were held to: **a flag gates
behaviour, never storage.** `CODEONBOARD_TUTOR` still owes it, and
`backend/learning/store.py` still reads no environment at all —
`tests/test_gap_model.py::test_the_persistence_path_reads_no_feature_flag`
asserts that structurally. Gap data written under the old flag loads unchanged.
