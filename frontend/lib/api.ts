const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** FastAPI puts the useful part in `detail`, which may be a string or an
 *  object carrying the pipeline's error list. Raw JSON in a UI is useless, so
 *  unwrap it to something a person can read. */
async function fail(res: Response): Promise<never> {
  const raw = await res.text();
  let message = raw;
  try {
    const body = JSON.parse(raw);
    const detail = body?.detail ?? body;
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail?.errors) && detail.errors.length > 0) {
      message = detail.errors.join("\n");
    } else if (typeof detail?.error === "string") message = detail.error;
  } catch {
    /* not JSON — the raw body is the best we have */
  }
  throw new Error(message.trim() || `Request failed (${res.status})`);
}

/** A request that never reached the server — backend down, or the page is on an
 *  origin its CORS list doesn't allow. The browser collapses both into an
 *  opaque `TypeError: Failed to fetch`, so translate it into a slug the UI can
 *  render as something a person can act on. */
async function send(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${BASE}${path}`, init);
  } catch {
    throw new Error("server_unreachable");
  }
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await send(path, {
    method: "POST",
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
}

export const sessionStart = (
  repo_url: string,
  goal: Record<string, string>,
  force_new = false,
  progress_id?: string,
) =>
  post<SessionStartResponse>("/session/start", {
    repo_url,
    goal,
    force_new,
    progress_id,
  });

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
}

export interface Lesson {
  node_id: string;
  lesson: LessonBody;
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
  /** Journey completion — separate from readiness, and neither gates the other. */
  complete?: boolean;
  /** Present only on a verification reply: ids this answer closed / left open. */
  kind?: string;
  resolved?: string[];
  unresolved?: string[];
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
