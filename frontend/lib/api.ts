/**
 * Every call goes through the Next.js rewrite (see `next.config.ts`), so the
 * browser only ever talks to its own origin and the auth cookie is first-party.
 *
 * There is no `NEXT_PUBLIC_API_URL` any more: that value was baked into the
 * browser bundle at build time, which both published the API's address and made
 * it impossible to change without a rebuild. The server-side `API_ORIGIN` in
 * `next.config.ts` replaces it.
 */
const BASE = "/api";

/** FastAPI puts the useful part in `detail`, which may be a string or an
 *  object carrying the pipeline's error list. Raw JSON in a UI is useless, so
 *  unwrap it to something a person can read. */
async function fail(res: Response, prefetched?: string): Promise<never> {
  // `prefetched` is the body when the caller has already read it. A Response
  // body can only be read once, and `send()` has to read a 401's before it can
  // tell a lost session from a refused password.
  const raw = prefetched ?? (await res.text());
  let message = raw;
  let isJson = false;
  try {
    const body = JSON.parse(raw);
    isJson = true;
    const detail = body?.detail ?? body;
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail?.errors) && detail.errors.length > 0) {
      message = detail.errors.join("\n");
    } else if (typeof detail?.error === "string") message = detail.error;
  } catch {
    /* not JSON — the raw body is the best we have */
  }
  // A 5xx whose body is not JSON did not come from FastAPI, which answers every
  // error it handles with a JSON `detail`. It is the Next.js `/api/*` rewrite
  // (see `next.config.ts`) failing to reach the backend at all, and its body is
  // the bare string "Internal Server Error".
  //
  // `send()` already turns an unreachable backend into `server_unreachable`, but
  // it only sees failures where the BROWSER's fetch rejects — which needs
  // Next.js itself to be down. With the rewrite in front, a dead FastAPI is a
  // perfectly successful request to Next that happens to return 500, so that
  // branch never fired and the proxy's own text was rendered as if the server had
  // said it. On the login form that made a dead backend look exactly like a
  // rejected password.
  //
  // An unhandled exception INSIDE FastAPI lands here too: Starlette answers it
  // with the same plain-text "Internal Server Error", so the two cannot be told
  // apart from the response alone. Reporting both as unreachable is the
  // deliberate trade — it names a cause the reader can actually check, and
  // the backend is where they have to look either way.
  if (!isJson && res.status >= 500) throw new Error("server_unreachable");
  throw new Error(message.trim() || `Request failed (${res.status})`);
}

/** A request that never reached the server — backend down, or the page is on an
 *  origin its CORS list doesn't allow. The browser collapses both into an
 *  opaque `TypeError: Failed to fetch`, so translate it into a slug the UI can
 *  render as something a person can act on. */
/** Thrown on any 401. The auth layer catches it once, centrally. */
export class NotAuthenticatedError extends Error {
  constructor() {
    super("not_authenticated");
    this.name = "NotAuthenticatedError";
  }
}

/** Notified whenever a request comes back 401, so the app reacts in ONE place. */
let onUnauthenticated: (() => void) | null = null;
export function setUnauthenticatedHandler(handler: (() => void) | null) {
  onUnauthenticated = handler;
}

/** The `detail` string of a FastAPI error body, or null if the body is not one
 *  (no JSON, or a `detail` that is an object rather than a slug). */
function detailOf(raw: string): string | null {
  try {
    const detail = JSON.parse(raw)?.detail;
    return typeof detail === "string" ? detail : null;
  } catch {
    return null;
  }
}

async function send(path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    // `credentials: "include"` on every request, in the ONE place every request
    // passes through. Per-call would work until the call somebody adds next
    // month forgets it — and that call would fail as "not signed in" rather
    // than as a missing option, which is a long way from its cause.
    res = await fetch(`${BASE}${path}`, { ...init, credentials: "include" });
  } catch (e: unknown) {
    // An abort is the CALLER'S decision, not a failure to reach the server, and
    // collapsing the two would make "I changed my mind" render as "the backend
    // is down". Rethrown as-is so callers can recognise it by name.
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new Error("server_unreachable");
  }
  if (res.status === 401) {
    // TWO DIFFERENT THINGS ARRIVE AS 401, AND ONLY ONE OF THEM IS A SESSION.
    //
    // `auth/deps.py` and the catch-all in `api.py` answer a missing, expired or
    // revoked cookie with the slug `not_authenticated`. A REFUSED CREDENTIAL —
    // a wrong password at `/auth/login`, a spent reset link — is also a 401,
    // but it carries its own message and says nothing about the session.
    //
    // Collapsing both into NotAuthenticatedError rendered a rejected password
    // as "Your session has ended. Sign in again." on a form the reader had just
    // typed their password into: it named a problem they did not have, offered
    // "sign in again" as the fix for the thing that had just failed, and hid
    // the one fact they needed. So judge the body, not the status.
    const raw = await res.text();
    const detail = detailOf(raw);
    // A 401 with no readable `detail` is treated as the session: that is the
    // overwhelmingly common one, and it is the one with a recovery path.
    if (detail === null || detail === "not_authenticated") {
      // The session is gone — expired, revoked, or never there. Reported once,
      // here, so no caller has to remember that 401 is the special one.
      onUnauthenticated?.();
      throw new NotAuthenticatedError();
    }
    // A refusal of what was just submitted. It gets to speak for itself.
    await fail(res, raw);
  }
  return res;
}

async function post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await send(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal,
  });
  if (!res.ok) await fail(res);
  return res.json();
}

async function patch<T>(path: string, body?: unknown): Promise<T> {
  const res = await send(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) await fail(res);
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await send(path);
  if (!res.ok) await fail(res);
  return res.json();
}

// --- Repository ---

export interface RepoCheck {
  ok: boolean;
  reason: string | null;
}

export const checkRepo = (repo_url: string) =>
  post<RepoCheck>("/repo/check", { repo_url });

// --- Goal dialogue ---

export interface Question {
  text: string;
  options: string[] | null;
  /** 1-based position in the interview. */
  index: number;
  /** Question count; a lower bound until goal_type is known. */
  total: number;
}

export interface StartResponse {
  session_id: string;
  question: Question;
}

export interface AnswerResponse {
  done: boolean;
  question?: Question;
  goal?: Record<string, string>;
}

export const goalStart = (repo_url: string) =>
  post<StartResponse>("/goal/start", { repo_url });

export const goalAnswer = (session_id: string, answer: string) =>
  post<AnswerResponse>("/goal/answer", { session_id, answer });

/** The question stepped back to, plus the answer already given for it. */
export interface BackResponse {
  question: Question;
  answer: string;
}

export const goalBack = (session_id: string) =>
  post<BackResponse>("/goal/back", { session_id });

// --- Session ---

export interface SessionStartResponse {
  session_id: string;
  /** "generating" — planning runs in the background (multi-user M7). */
  status?: string;
  progress_id?: string;
}

export const sessionStart = (
  repo_url: string,
  goal: Record<string, string>,
  force_new = false,
  progress_id?: string,
  /**
   * Abandon the wait. The run itself is NOT cancelled — the backend keeps
   * cloning and planning, and the session it writes is simply never navigated
   * to. That is the honest shape of it: the only thing a client can withdraw
   * here is its own interest in the answer.
   */
  signal?: AbortSignal,
) =>
  post<SessionStartResponse>(
    "/session/start",
    { repo_url, goal, force_new, progress_id },
    signal,
  );

/** Live progress of an in-flight /session/start, polled with the same
 *  `progress_id` that request was sent with.
 *
 *  `stages` is the backend's own vocabulary and order — render from it rather
 *  than from a hardcoded list, so a pipeline that grows a stage shows it.
 *  `stage` is null before the first one lands and once the run has finished. */
export interface PipelineProgress {
  stages: string[];
  stage: string | null;
  done: string[];
  /** The exploration's last tool call: which tool, and what it looked at. */
  activity: { tool: string; target: string } | null;
  turn: number;
  calls: number;
  seconds: number;
  finished: boolean;
}

export const sessionProgress = (progress_id: string) =>
  get<PipelineProgress>(`/session/progress/${encodeURIComponent(progress_id)}`);

/** What a reset threw away. Counts, not content — nothing is archived. */
export interface DiscardedWork {
  stops: number;
  attempts: number;
  gaps: number;
  remedial_nodes: number;
  lessons_restored: number;
}

export interface ResetResponse {
  session_id: string;
  graph: SessionGraph;
  discarded: DiscardedWork;
}

/**
 * Start over: the same learning path, restored, with none of the learner's work.
 *
 * Nothing like `sessionStart(force_new)`, which is the *rebuild* — this runs no
 * pipeline, spends no model call, keeps the session id and returns in
 * milliseconds. It carries no progress id and needs no abort signal for the same
 * reason: there is no wait to report on, and nothing to withdraw from.
 *
 * The response carries the whole graph, in the shape `getSession` returns, so the
 * caller swaps it in rather than re-fetching.
 */
export const resetSession = (session_id: string) =>
  post<ResetResponse>(`/session/${encodeURIComponent(session_id)}/reset`);

// --- Learning graph ---

export type UnderstandingState = "not_started" | "failed" | "partial" | "understood";

export type Classification = "understood" | "partial" | "confused" | "off-topic";

/** One graded answer. Append-only, oldest first. */
export interface Attempt {
  answer: string;
  classification: Classification;
  rationale: string;
  /**
   * WHY the answer fell short, not just how far. Already on the wire — the
   * backend has recorded it on every attempt since B5; this type simply did
   * not declare it.
   */
  gap_kind?: string;
  /**
   * "assessment" (an answer to the lesson's own question) or "verification" (an
   * answer to a fresh question about ONE gap — gap-model M6).
   *
   * The two must never be pooled: a verification answer is evidence about a gap,
   * not a second attempt at the objective, so averaging or counting them together
   * misreports both. Optional because every attempt written before verification
   * existed is an assessment, which makes the absent case a fact rather than a
   * guess.
   */
  kind?: string;
  /**
   * THE QUESTION THIS ANSWERED, and which mechanism asked it.
   *
   * Optional, and absent means UNRECORDED rather than "there was no question":
   * every attempt written before M1 has neither. A surface must therefore fall
   * back to showing nothing, never to showing the node's CURRENT prompt — after
   * a re-teach that is a different question from the one the learner answered,
   * and captioning an old answer with it would be a confident lie.
   *
   * `question_source` is "lesson" | "reteach" | "verification" | "reassessment".
   * Three of the four produce an assessment, so this is a separate axis from
   * `kind`, not a restatement of it.
   */
  question?: string;
  question_source?: string;
  /**
   * What the system DID about this answer.
   *
   * Already on the wire — `to_dict` ships `n.attempts` as recorded, and
   * `record_response` has written this since M2; the type simply did not declare
   * it. The half that matters here is `superseded_lesson`: a re-teach overwrites
   * `cached_lesson`, so without this the version that misled the learner is gone
   * and "how their understanding moved" loses one side.
   */
  response?: {
    action?: string;
    retaught?: boolean;
    text?: string;
    /**
     * The gap ids this response was written to correct.
     *
     * Already on the wire — `record_response` has written it since M2 of the gap
     * model — and undeclared until now. Joined against `node.gaps` it is what
     * lets a rewritten lesson say WHICH misconception it answers, rather than
     * only that something changed. No new field, no new model call: the two
     * halves were simply never put together.
     */
    gaps_addressed?: string[];
    gaps_opened?: string[];
    /** On a VERIFICATION attempt: the gaps this answer actually closed. */
    gaps_resolved?: string[];
    superseded_lesson?: {
      setup?: string | null;
      walkthrough?: string | null;
      prompt?: string | null;
      reveal?: string | null;
      takeaway?: string | null;
    } | null;
    at?: string;
  };
  /** ISO-8601, UTC. */
  at: string;
}

/** Where a unit came from. Warm-ups are detours, not stops on the journey. */
export type Origin = "planned" | "system_remediation" | "learner_request";

/** One warm-up, and the unit it was spliced in to unblock. */
export interface Detour {
  node_id: string;
  title: string;
  origin: Origin;
  unlocks: string | null;
  understanding_state: UnderstandingState;
}

/**
 * The two measures, computed server-side so there is exactly one implementation
 * of each definition (learning-graph.md §5.4).
 *
 *   goal_readiness    evidence-weighted mastery of what the goal REQUIRES.
 *                     Moves only when evidence about the learner changes.
 *   journey_progress  how much of the planned walk has been dealt with.
 *                     Coverage, not mastery.
 *
 * Neither counts remedial warm-ups: they are reported in `detours`.
 */
export interface Progress {
  goal_readiness: number; // 0.0 – 1.0
  core_total: number;
  /** Demonstrated coverage of the required set — the headline (Model A′). */
  core_demonstrated: number;
  /** Assessed and not yet demonstrated. Shown beside the headline, never in it. */
  core_in_progress: number;
  core_unassessed: number;
  journey_progress: number; // 0.0 – 1.0
  stops_settled: number;
  stops_total: number;
  assessed_coverage: number;
  assessed: number;
  detours: Detour[];
  skipped: number;
  optional_total: number;
  optional_completed: number;
}

/**
 * TWO DIMENSIONS, never one (learning-graph.md M3a.1).
 *
 * `UnderstandingClass` is what the EVIDENCE demonstrates. `Disposition` is what
 * the learner DECIDED about remediation. They are independent: a waived gap can
 * later be verified, leaving a node genuinely demonstrated while the record
 * still says the learner had chosen to stop.
 */
export type UnderstandingClass =
  | "strength"      // demonstrated, never fell short here
  | "recovered"     // fell short, then demonstrated — NOT a weakness
  | "unresolved"    // assessed and not demonstrated
  | "insufficient"; // no usable evidence either way

export type Disposition =
  | "active"     // nothing decided; help is still on offer
  | "continued"  // "I'll move on" — withdrawn by a new attempt
  | "waived"     // "stop asking me"
  | "skipped"
  | "asserted";  // claimed, not demonstrated

export type StateTally = Record<UnderstandingClass, number>;

/** One row of the Understanding Profile. */
export interface UnderstandingRow {
  node_id: string;
  title: string;
  objective: string;
  understanding: UnderstandingClass;
  disposition: Disposition;
  /** The derived `understanding_of` value — the single owner of this question. */
  state: UnderstandingState;
  attempts: number;
  evidence_count: number;
  /** null means UNKNOWN (pre-M2), never "no help was given". */
  interventions: (string | null)[] | null;
  first_answer: Classification | null;
  /**
   * False when the latest answer reached the objective but the unit is still
   * held back — gap-model M7 doing its job. Without gaps on the wire the UI can
   * say THAT honestly, but not why.
   */
  state_matches_latest_answer: boolean;
  area_id: string;
  kind: string;
  /**
   * Why the state is what it is, when the latest answer alone does not explain
   * it (gap-model M9). `state_matches_latest_answer` reports the discrepancy;
   * these report its cause — which is exactly what the drawer could not say
   * before gap content reached the wire.
   */
  gaps_open?: number;
  /** Unverified AND blocking: the count that holds a stop back. */
  gaps_blocking?: number;
  gaps_verified?: number;
  gaps_waived?: number;
  /** A fresh question has been issued and is awaiting an answer. */
  verification_pending?: boolean;
}

/**
 * One L2 pattern — a repeated observation over the evidence (M3a.2).
 *
 * `detail` carries NUMBERS ONLY; the sentence is composed in `strings.ts`. That
 * split is deliberate: the wording is the part that can over-claim, so it lives
 * in one reviewable place rather than in aggregation code.
 *
 * `evidence` is never empty — a template that cannot enumerate its support does
 * not fire.
 */
export interface Pattern {
  template:
    // M3a.2 — read ANSWERS (classification, the scalar gap_kind)
    | "kind_contrast" | "recurring_shortfall" | "area_evidence"
    // M3b — read the GAP OBJECTS themselves: named misconceptions with a
    // lifecycle. A different evidence base answering a different question.
    | "gap_outcomes" | "blocking_backlog" | "verification_outcomes"
    | "remediation_closure";
  detail: Record<string, string | number>;
  evidence: { node_id: string; attempt_index: number }[];
}

export interface UnderstandingProfile {
  /** Usually empty: thresholds are set so a handful of answers produces none. */
  patterns: Pattern[];
  /**
   * Gap-derived observations (M3b). A separate list so a consumer with no gap
   * data can ignore them wholesale, and so the two evidence bases stay
   * distinguishable. Empty on every session written before the gap model.
   */
  gap_patterns: Pattern[];
  totals: StateTally;
  /** Units carrying real evidence — the honest denominator for the profile. */
  assessed: number;
  total: number;
  by_area: Record<string, StateTally>;
  by_kind: Record<string, StateTally>;
  /** Unresolved AND still an open task. */
  needs_work: string[];
  /** Unresolved, but the learner deliberately closed the question. */
  set_aside: string[];
  recovered: string[];
  nodes: UnderstandingRow[];
}

/** One step of the evidence chain behind a node's state. */
export interface EvidenceStep {
  index: number;
  kind: string;
  /**
   * What was asked, and by which mechanism. `null` where unrecorded (pre-M1).
   *
   * The link the chain was missing: the drawer exists to make a state traceable,
   * and an answer with no question above it leaves the reader guessing which of
   * up to three different questions on this node produced the verdict.
   */
  question: string | null;
  question_source: string | null;
  answer: string;
  classification: Classification;
  rationale: string;
  graded: boolean;
  counts_as_evidence: boolean;
  /** null = no record (pre-M2). "none" = recorded, nothing was owed. */
  intervention: string | null;
  intervention_text: string | null;
  superseded_lesson: LessonBody | null;
  at: string;
}

export interface EvidenceChain extends UnderstandingRow {
  timeline: EvidenceStep[];
  journey_events: JourneyEvent[];
  /**
   * Every gap on the stop, settled ones included — the drawer explains a STATE,
   * and "this was waived" or "this was verified" is as much a part of that
   * explanation as what is still open.
   */
  gaps?: GapDetail[];
}

export interface JourneyEvent {
  kind: string;
  at: string;
  nodes?: string[];
  cause?: { node_id: string; attempt_index: number };
  origin?: Origin;
  unlocks?: string;
  /** `jumped` only: the stop left behind, null when there was none. */
  from_node_id?: string | null;
  /** `jumped` only: `"study"` left the route, `"resume"` rejoined it. */
  intent?: string;
}

export const getEvidence = (session_id: string, node_id: string) =>
  get<EvidenceChain>(`/session/${session_id}/evidence/${node_id}`);

/** One verified location a unit is grounded in. */
export interface Anchor {
  file: string;
  symbol: string | null;
  line_start: number;
  line_end: number;
}

export interface GraphNode {
  id: string;
  title: string;
  /**
   * The DISPLAY anchor — where the code pane opens by default. A unit may be
   * grounded in several equally real locations; this one carries no claim to
   * being the most important. `anchors` below is the full set.
   */
  file: string;
  line_start: number;
  line_end: number;
  /** Empty on graphs planned before multi-anchor units existed. */
  anchors?: Anchor[];
  /** The unit's primary kind. Empty string on pre-B3 graphs. */
  kind?: string;
  /** "required" | "recommended" | "optional". Empty on pre-B3 graphs. */
  priority?: string;
  /** Which area this unit belongs to. Empty on pre-B3 graphs. */
  area_id?: string;
  concept_tags: string[];
  /**
   * The claim this unit exists to make the learner able to make — the contract
   * between the Planner, Teaching and the Grader, and the standard an answer is
   * marked against. Falls back to `understand` server-side on pre-B3 graphs.
   */
  objective?: string;
  /**
   * What the learner ASSERTED about their own understanding ("skip" |
   * "mark_understood" | "mark_weak"), kept distinct from what they
   * demonstrated. Null when the system's own state is authoritative.
   */
  user_override?: string | null;
  /** "planned" for an ordinary stop; anything else is a warm-up. */
  origin?: Origin;
  /**
   * What the evidence demonstrates, and what the learner decided about
   * remediation. Computed server-side so every surface renders the SAME
   * classification — deriving it locally from `weak_spot` is what captioned
   * recovered units "marked weak" permanently.
   */
  understanding?: UnderstandingClass;
  disposition?: Disposition;
  /**
   * Has the learner answered this stop's own question at least once?
   *
   * The third fact, and not derivable from the two above: `insufficient` covers
   * both "never opened" and "answered, and the answer told us nothing" — an
   * `off-topic` answer is deliberately excluded from evidence — and those are the
   * two stops a learner most needs to tell apart. Assessments only, decided
   * server-side, so no surface counts `attempts` with a rule of its own.
   *
   * Optional: absent on a graph served by a build older than this field.
   * `standingOf` reads that as "not attempted", which is the pre-M0 rendering.
   */
  attempted?: boolean;
  understanding_state: UnderstandingState;
  visited: boolean;
  /** Sticky: true once the learner ever failed here. HISTORY, not current
   *  state — use `understanding` to decide what to show. */
  weak_spot: boolean;
  has_lesson: boolean;
  attempts: Attempt[];
  /**
   * What the learner does not know here, by name (gap-model M9) — and what they
   * have since PUT RIGHT. Every gap on the stop, whatever its status.
   *
   * This used to be open-only, which made the list a debt column: a gap the
   * learner closed left the wire the instant it closed, so the ledger could
   * only ever grow or silently shrink. Filter on `status` for outstanding work
   * (`openOnly` below); render the rest as the record of what was fixed.
   *
   * This is what lets a stop carrying unresolved misconceptions read differently
   * from one nobody has touched; before M9 both rendered as "not done".
   */
  gaps?: NodeGap[];
}

/** A misconception, as a stop carries it, with its lifecycle. */
export interface NodeGap {
  id: string;
  /** "wrong_model" | "missing_prerequisite" | "right_idea_wrong_altitude". */
  kind: string;
  /** The false claim itself, in the learner's own terms. */
  claim: string;
  /** Does it hold the stop back from counting as demonstrated? */
  blocking: boolean;
  /**
   * "open" | "verified" | "waived". Only `verified` permits `understood`, and
   * only a fresh verification answer can produce it. Optional because a session
   * graded before the status reached this payload has none.
   */
  status?: string;
  /** Which clause of the objective the claim violates. May be empty. */
  objective_part?: string;
  /** How many verification questions have been spent on it. */
  verification_attempts?: number;
  /**
   * The SYSTEM has stopped proposing checks for this one. It does not stop the
   * learner asking: "Check this" targets a gap by id, which bypasses the cap.
   */
  exhausted?: boolean;
  opened_at?: string;
  closed_at?: string | null;
}

/** Outstanding work only. A gap with no `status` predates the field and is open. */
export const openOnly = (gaps: NodeGap[] | undefined): NodeGap[] =>
  (gaps ?? []).filter((g) => (g.status ?? "open") === "open");

/** A gap with its full lifecycle, as the evidence drawer receives it. */
export interface GapDetail extends NodeGap {
  objective_part: string;
  /** "open" | "verified" | "waived". Only `verified` permits `understood`. */
  status: string;
  verification_attempts: number;
  /** The system has stopped proposing checks for this one. */
  exhausted: boolean;
  opened_at: string;
  closed_at: string | null;
  /** Indices into the evidence timeline. */
  origin_attempt: number;
  resolved_by: number | null;
}

/** One level of curriculum grouping. Empty list on pre-B3 graphs. */
export interface Area {
  id: string;
  title: string;
  why: string;
  order: number;
}

export interface GraphEdge {
  from_id: string;
  to_id: string;
  kind: string;
}

export interface SessionGraph {
  session_id: string;
  repo_url: string;
  goal: Record<string, string>;
  current_node_id: string | null;
  /**
   * Whether this session has its original plan on disk, and therefore whether
   * `Start over` can work at all.
   *
   * False for sessions planned before routes were snapshotted. Nothing is ever
   * fabricated for them — the honest answer is that this action is unavailable,
   * and rebuilding is the way to a route that can be restarted.
   */
  has_plan?: boolean;
  nodes: GraphNode[];
  edges: GraphEdge[];
  areas?: Area[];
  /**
   * RETAINED and equal to `progress.goal_readiness`. Prefer `progress` — this
   * key exists so nothing that already reads it breaks.
   */
  readiness: number; // 0.0 – 1.0
  progress: Progress;
  understanding: UnderstandingProfile;
  journey_events?: JourneyEvent[];
  /**
   * How the learner reached the current stop, when that is worth saying — null
   * whenever they simply walked here, and on every session written before this
   * existed. See `lib/arrival.ts` for what is derived from it.
   */
  arrival?: Arrival | null;
}

/**
 * The raw arrival fact, straight off the wire. Deliberately carries no direction,
 * position or count: those are read off the ROUTE by `arrivalNotice`, using the
 * same `buildRoute` that numbers the rail, so the notice and the rail cannot
 * disagree about which stop this is.
 */
export interface Arrival {
  /** The stop landed on. Compared against `current_node_id` before anything is shown. */
  node_id: string;
  /** Only `"jumped"` today. Named rather than boolean so a later kind is additive. */
  kind: string;
  /** The stop left behind, or null when there was none to leave. */
  from_node_id: string | null;
  at: string;
}

export const getSession = (session_id: string) =>
  get<SessionGraph>(`/session/${session_id}`);

// --- Welcome briefing ---

/** One thing worth knowing before starting, and where in the code it lives. */
export interface BriefingNote {
  text: string;
  /**
   * A path the backend checked against the checkout, or null. Null does not mean
   * the note is unanchored prose the model made up — it means the citation it
   * offered did not resolve and was dropped rather than shown on trust.
   */
  file: string | null;
}

export interface Briefing {
  paragraph: string;
  notes: BriefingNote[];
  /**
   * False when the paragraph is the repository survey's own architecture prose —
   * true, but written for nobody in particular. The page says which one this is
   * rather than claiming every briefing was written for this reader.
   */
  personalized: boolean;
  /** False when there was no grounded material to write a briefing from. */
  available: boolean;
}

/** First call writes the briefing (one Haiku call); later calls read it back. */
export const getWelcome = (session_id: string) =>
  get<{ briefing: Briefing }>(`/session/${session_id}/welcome`);

// --- Lesson ---

export interface LessonBody {
  /**
   * The whole lesson as one block. Always present: for a lesson written before
   * the setup/reveal split it is the only body there is, and for a split lesson
   * the backend assembles it from setup + reveal. Rendering it is the legacy
   * path — see LessonPanel.
   */
  walkthrough: string;
  prompt: string;
  prompt_kind: string;
  /** One line connecting to the unit just finished. Absent on pre-B4 lessons. */
  why_now?: string;
  /** Framing and code, WITHOUT the answer. Absent on pre-B4 lessons. */
  setup?: string;
  /** The explanation. Withheld until the learner has answered. */
  reveal?: string;
  /** The objective restated as something to remember. */
  takeaway?: string;
  /** What to hold yourself here versus what you can safely delegate. */
  ownership?: string;
  /**
   * An optional four-option rendering of `prompt`. Present only when the
   * question's form has a single statable answer; `[]` or absent everywhere
   * else, including every lesson taught before choices existed, and on a
   * degraded fallback lesson. The learner chooses at answer time whether to
   * pick an option or write their own — either way the text posted back is
   * graded against the objective, so no option is flagged here as the right one.
   */
  choices?: string[];
}

/**
 * What "Ask me again" would do here — computed by the backend, never by us.
 *
 * The panel used to reconstruct this from four partial flags (`canAnswerAgain`,
 * `checkAvailable`, `canRequestWarmUp`, `warmUpDeclined`), each derived from a
 * different slice of the grading reply, and every one of this pass's defects was
 * a seam between them. The facts they were approximating — gaps, budgets,
 * remediation rounds, which questions have been answered — all live on the
 * server, so the decision does too. See `backend/learning/retry.py`.
 */
export interface RetryOffer {
  available: boolean;
  /**
   * "verify"    a fresh question about one named misconception
   * "reassess"  a fresh question about the objective
   * "answer"    the unit's own prompt, never yet answered — the FIRST attempt,
   *             not a retry, and offered only while its reveal has never shown
   * null        nothing on offer; `reason` says why
   */
  mechanism: "verify" | "reassess" | "answer" | null;
  /** "objective_met" | "budget_spent" | "already_asked" | "not_applicable" | "" */
  reason: string;
  gap_id: string | null;
  reassessments_left: number;
}

/**
 * A question the stop is waiting on, shipped WITHOUT its answer.
 *
 * One shape for both mechanisms, because the client's job is identical either
 * way — show this, post the answer back with this `kind`. Two fields would mean
 * two places to look for one question, and eventually only one of them checked.
 */
export interface PendingQuestion {
  kind: "verification" | "reassessment";
  question: string;
  /**
   * Four options for a re-assessment question, or `[]`. A verification question
   * is always `[]`; absent from a backend older than this. Not an answer key — a
   * pick is graded against the objective like typed text; see `LessonBody.choices`
   * and D10.
   */
  choices?: string[];
}

export interface Lesson {
  node_id: string;
  lesson: LessonBody;
  /** Absent from a backend older than M2. */
  retry?: RetryOffer;
  pending?: PendingQuestion | null;
}

export const getLesson = (session_id: string) =>
  get<Lesson>(`/session/${session_id}/lesson`);

// --- Respond ---

export interface Mutation {
  kind: "prerequisite" | "skip" | "none";
  reason?: string;
}

/** How the system responded to the gap, decided from `gap_kind`. */
export interface Adaptation {
  kind: "none" | "hint" | "reteach" | "prerequisite" | "followup";
  /** The hint or follow-up itself. Null when generating it failed. */
  text?: string | null;
  /** Whether the corrected lesson was written; the panel reloads if so. */
  retaught?: boolean;
  /** How many units ahead were demoted after sustained understanding. */
  pruned?: number;
}

export interface RespondResult {
  classification: Classification;
  /** Why the answer fell short — what the adaptation was chosen from. */
  gap_kind?: string;
  rationale: string;
  understanding_state: string;
  /** Only a missing foundation grows the graph; everything else is `none`. */
  mutation: Mutation;
  adaptation?: Adaptation;
  current_node_id: string | null;
  /** Every gap on the graded stop after this answer, settled ones included. */
  gaps?: NodeGap[];
  /**
   * The ids THIS ANSWER opened — the subset of `gaps` that did not exist a
   * moment ago.
   *
   * Server-computed and server-sent, rather than diffed here against the gaps
   * the panel happened to be holding: "which of these is new" is a fact about
   * two points in time, and a client only reliably has one of them. Optional
   * because a pre-fix backend does not send it, and absent must read as
   * UNKNOWN — a surface that treated it as "none" would silently stop
   * announcing new gaps against an older server.
   */
  gaps_opened?: string[];
  /** Journey completion — separate from readiness, and neither gates the other. */
  complete?: boolean;
  /** Present only on a verification reply: ids this answer closed / left open. */
  kind?: string;
  resolved?: string[];
  unresolved?: string[];
  /** What to offer next, recomputed after this answer. Absent pre-M2. */
  retry?: RetryOffer;
}

export const respond = (session_id: string, answer: string, node_id?: string) =>
  post<RespondResult>(`/session/${session_id}/respond`, {
    response: answer,
    node_id,
  });

/**
 * A FRESH question about one gap. Replaces "Try again", which re-showed the
 * question the learner had already been given the answer to.
 */
export interface VerificationPrompt {
  node_id: string;
  question: string;
  targets: string[];
  gaps: NodeGap[];
}

/**
 * Ask for a check. Omit `gap_id` and the server picks the leading gap; pass one
 * and the learner picked it from the list by name, which also bypasses the
 * two-question cap — that cap bounds the system's nagging, not their appetite.
 */
export const requestVerification = (
  session_id: string,
  node_id?: string,
  gap_id?: string,
) => post<VerificationPrompt>(`/session/${session_id}/verify`, { node_id, gap_id });

/**
 * Ask for a fresh question about the OBJECTIVE, after a shortfall.
 *
 * The sibling of `requestVerification`, one level up, and the route for the
 * shortfall that named no gap — which is most of them. Ships no answer, and is
 * charged on issue.
 */
export const requestReassessment = (session_id: string, node_id?: string) =>
  post<{ node_id: string; question: string; choices?: string[]; retry: RetryOffer }>(
    `/session/${session_id}/reassess`,
    { node_id },
  );

/**
 * Answer a re-assessment. Graded as an ORDINARY ASSESSMENT of the objective —
 * same standard, same effect on state — which is the whole point: a second
 * question about the objective is not a special kind of evidence.
 */
export const respondToReassessment = (
  session_id: string,
  answer: string,
  node_id?: string,
) =>
  post<RespondResult>(`/session/${session_id}/respond`, {
    response: answer,
    node_id,
    kind: "reassessment",
  });

/** Answer a verification question. Graded against the gaps, not the objective. */
export const respondToVerification = (
  session_id: string,
  answer: string,
  node_id?: string,
) =>
  post<RespondResult>(`/session/${session_id}/respond`, {
    response: answer,
    node_id,
    kind: "verification",
  });

export interface WaiveResult {
  node_id: string;
  /** Named, never a bare count — "what you chose not to check". */
  waived: string[];
  gaps: NodeGap[];
  understanding_state: string;
  readiness: number;
  complete: boolean;
}

/** Stop the system asking: one gap, or every open one on the stop. */
export const waive = (session_id: string, gap_id?: string, node_id?: string) =>
  post<WaiveResult>(`/session/${session_id}/waive`, { gap_id, node_id });

// --- Advance ---

export const advance = (session_id: string, signal: "next" | "skip" = "next", node_id?: string) =>
  post(`/session/${session_id}/advance`, { signal, node_id });

// --- Scope control (U4) ---

export interface ScopeResult {
  direction: "shorter" | "deeper";
  changed: number;
  journey_size_before: number;
  journey_size: number;
  readiness: number;
  /** False when there was nothing left to move in that direction. */
  applied: boolean;
}

export const setScope = (session_id: string, direction: "shorter" | "deeper") =>
  post<ScopeResult>(`/session/${session_id}/scope`, { direction });

/**
 * Move to a stop that is not the next one.
 *
 * `intent` is the difference between leaving the route and rejoining it:
 * `"study"` raises the arrival notice on the stop landed on, `"resume"` clears it.
 * Both are recorded — a log that showed only departures would imply the learner
 * never came back.
 */
export const jump = (
  session_id: string,
  node_id: string,
  intent: "study" | "resume" = "study"
) =>
  post<{ current_node_id: string; arrival: Arrival | null }>(
    `/session/${session_id}/jump`,
    { node_id, intent }
  );

export const retry = (session_id: string, node_id?: string) =>
  post<{ current_node_id: string; inserted: boolean }>(`/session/${session_id}/retry`, { node_id });

// --- File viewer ---

export interface FileContent {
  path: string;
  content: string;
}

export const getFile = (session_id: string, path: string) =>
  get<FileContent>(`/session/${session_id}/file?path=${encodeURIComponent(path)}`);


// --- Authentication (multi-user M2) ---

export interface AuthUser {
  user_id: string;
  email: string | null;
  display_name: string | null;
}

export const register = (email: string, password: string, display_name?: string) =>
  post<AuthUser>("/auth/register", { email, password, display_name });

export const login = (email: string, password: string) =>
  post<AuthUser>("/auth/login", { email, password });

/** Ask for a reset link.
 *
 *  `reset_url` is populated only outside production, where it IS the delivery
 *  mechanism — this build mails nothing. It is null for an address with no
 *  password account, and null in production for every address, so the caller
 *  must treat "no link" as the ordinary case rather than as a failure. */
export const requestPasswordReset = (email: string) =>
  post<{ reset_url: string | null }>("/auth/forgot", { email });

/** Spend a reset token. Succeeds into a signed-in session, like `login`. */
export const resetPassword = (token: string, password: string) =>
  post<AuthUser>("/auth/reset", { token, password });

/**
 * Who is calling, or null when nobody is. The whole client-side auth model.
 *
 * Returns null rather than throwing on 401: "not signed in" is the expected
 * ANSWER to this question, not a failure to answer it. Every other endpoint
 * treats a 401 as exceptional, which is why this one unwraps it here.
 */
export const me = async (): Promise<AuthUser | null> => {
  try {
    return await get<AuthUser>("/auth/me");
  } catch (err) {
    if (err instanceof NotAuthenticatedError) return null;
    throw err;
  }
};

/** Ends this session. Never fails from the caller's point of view. */
export const logout = async (): Promise<void> => {
  try {
    await send("/auth/logout", { method: "POST" });
  } catch {
    /* already signed out, or the server is unreachable — either way, done */
  }
};

export const logoutEverywhere = () => post<void>("/auth/logout/all");


// --- The session list (multi-user M4/M5) ---

/**
 * One dashboard card's worth of a session.
 *
 * `progress` values are NULLABLE and null means NOT COMPUTED — a session
 * migrated from before the cache existed and not saved since. Rendering that as
 * 0% would be a claim about the learner rather than about the cache, so the UI
 * shows nothing at all for it.
 */
export interface SessionSummary {
  session_id: string;
  repo_url: string;
  repo_id: string | null;
  goal: Record<string, string>;
  title: string | null;
  status: string | null;
  current_node_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  last_active_at: string | null;
  archived_at: string | null;
  /**
   * The welcome briefing's opening — what this repository is, pitched at this
   * learner. NULL for a session whose welcome page was never opened, and the
   * card then says nothing about the repository rather than describing one
   * nothing has read.
   */
  repo_blurb: string | null;
  progress: {
    goal_readiness: number | null;
    stops_settled: number | null;
    stops_total: number | null;
  };
}

export const listSessions = (includeArchived = false) =>
  get<{ sessions: SessionSummary[] }>(
    `/sessions${includeArchived ? "?include_archived=true" : ""}`,
  );

export const getSessionSummary = (session_id: string) =>
  get<SessionSummary>(`/sessions/${encodeURIComponent(session_id)}`);

export const renameSession = (session_id: string, title: string) =>
  patch<SessionSummary>(`/sessions/${encodeURIComponent(session_id)}`, { title });

export const archiveSession = (session_id: string, archived: boolean) =>
  patch<SessionSummary>(`/sessions/${encodeURIComponent(session_id)}`, { archived });

/** Irreversible. The dashboard confirms before calling this. */
export const deleteSession = async (session_id: string): Promise<void> => {
  const res = await send(`/sessions/${encodeURIComponent(session_id)}`, {
    method: "DELETE",
  });
  if (!res.ok) await fail(res);
};


// --- Google (multi-user M6) ---

export interface Identities {
  identities: { provider: string; created_at: string }[];
  google_configured: boolean;
}

export const listIdentities = () => get<Identities>("/auth/identities");

/** Which ways of signing in this server offers. Readable before sign-in.
 *
 *  The sign-in page needs this BEFORE anybody is authenticated, which is why it
 *  is its own public endpoint rather than a field on `/auth/identities`. */
export const listProviders = () =>
  get<{ password: boolean; google: boolean }>("/auth/providers");

/**
 * Finish a Google sign-in that collided with an existing password account.
 *
 * Google proved the EMAIL; this proves the ACCOUNT. Both are required because
 * the app verifies no email of its own, so an address in `users.email` is an
 * unverified claim and linking on it alone would be an account takeover.
 */
export const linkGoogle = (password: string) =>
  post<AuthUser>("/auth/google/link", { password });

export const unlinkGoogle = async (): Promise<void> => {
  const res = await send("/auth/identities/google", { method: "DELETE" });
  if (!res.ok) await fail(res);
};

/** A full navigation, not a fetch — the browser has to follow Google's redirect. */
export const GOOGLE_START = "/api/auth/google/start";


// --- The Tutor (docs/planning/phases/tutor.md) ---
//
// Everything the panel renders is DECIDED BY THE SERVER: which mode it is in,
// whether a hint is available, whether the reveal is, what an offer would do.
// The frontend renders learning decisions; it does not compute them (D22), and
// the mode in particular must never be inferred client-side — a client that
// could name its own mode could ask for the answer key.

/** One place in the repository. The range is derived by the backend, never sent by a model. */
export interface TutorCitation {
  file: string;
  symbol: string | null;
  line_start: number;
  line_end: number;
}

/**
 * A validated offer — an existing action, rendered as one control.
 *
 * `label_key` names a string in `strings.ts` rather than carrying prose: the
 * backend decides WHICH action is offered and the frontend decides what it is
 * called, the same split as `retry.mechanism`.
 */
export interface TutorSuggestion {
  kind: "verify" | "reassess" | "jump" | "deepen";
  label_key: string;
  node_id: string | null;
  gap_id: string | null;
  /** Present only on a system offer: which deterministic signal produced it. */
  signal?: "dwelling" | "returning";
}

export interface TutorTurn {
  id: string;
  at: string;
  node_id: string | null;
  mode: "explain" | "scaffold";
  hint_level: number;
  question: string;
  answer: string;
  scope: "answered" | "out_of_scope" | "is_the_assessment";
  grounded: boolean;
  pinned: boolean;
  citations?: TutorCitation[];
  suggestion?: TutorSuggestion;
  usage?: Record<string, number>;
}

/**
 * Which Tutor is running, and everything a surface needs to say so.
 *
 * `can_hint` and `can_reveal` are the server's answers, not predicates to
 * re-derive: `can_reveal` is true from rung zero because the ladder bounds hints
 * rather than honesty, and a client that re-implemented that rule would get it
 * wrong the first time the ladder changed.
 */
export interface TutorMode {
  mode: "explain" | "scaffold";
  reason: string;
  question: string;
  question_source: string;
  hints_used: number;
  hints_left: number;
  revealed: boolean;
  can_hint: boolean;
  can_reveal: boolean;
}

export interface TutorState {
  mode: TutorMode;
  remaining: number;
  cap: number;
  node_id: string | null;
  offers: TutorSuggestion[];
  turn?: TutorTurn | null;
  /** Set when the call failed. No turn was stored and nothing was spent. */
  failed?: boolean;
  /** What to show when `failed` — an apology, never a fabricated answer. */
  text?: string;
}

export interface TutorTranscript extends TutorState {
  turns: TutorTurn[];
}

export interface TutorReveal extends TutorState {
  reveal: string;
  /** What the learner gets INSTEAD of the question they just spent. */
  retry: RetryOffer;
}

export const getTutor = (session_id: string) =>
  get<TutorTranscript>(`/session/${session_id}/tutor`);

export const askTutor = (session_id: string, question: string, node_id?: string) =>
  post<TutorState>(`/session/${session_id}/tutor/ask`, { question, node_id });

export const tutorHint = (session_id: string, node_id?: string) =>
  post<TutorState>(`/session/${session_id}/tutor/hint`, { node_id });

/**
 * Show the explanation, and spend the current question.
 *
 * The consequence is stated on the control that calls this, before it is pressed
 * — see `t.tutor.revealWarning`. Afterwards the learner is in exactly the state
 * any graded answer leaves them in, and `retry` on the response says what they
 * get next.
 */
export const tutorReveal = (session_id: string, node_id?: string) =>
  post<TutorReveal>(`/session/${session_id}/tutor/reveal`, { node_id });

export const tutorPin = (session_id: string, turn_id: string, pinned: boolean) =>
  post<{ turn: TutorTurn }>(`/session/${session_id}/tutor/pin`, { turn_id, pinned });
