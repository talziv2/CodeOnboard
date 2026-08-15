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

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) await fail(res);
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
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

// --- Session ---

export interface SessionStartResponse {
  session_id: string;
}

export const sessionStart = (repo_url: string, goal: Record<string, string>, force_new = false) =>
  post<SessionStartResponse>("/session/start", { repo_url, goal, force_new });

// --- Learning graph ---

export type UnderstandingState = "not_started" | "failed" | "partial" | "understood";

export type Classification = "understood" | "partial" | "confused" | "off-topic";

/** One graded answer. Append-only, oldest first. */
export interface Attempt {
  answer: string;
  classification: Classification;
  rationale: string;
  /** ISO-8601, UTC. */
  at: string;
}

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
  understanding_state: UnderstandingState;
  visited: boolean;
  weak_spot: boolean;
  has_lesson: boolean;
  attempts: Attempt[];
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
  readiness: number; // 0.0 – 1.0
}

export const getSession = (session_id: string) =>
  get<SessionGraph>(`/session/${session_id}`);

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
}

export const respond = (session_id: string, answer: string, node_id?: string) =>
  post<RespondResult>(`/session/${session_id}/respond`, {
    response: answer,
    node_id,
  });

// --- Advance ---

export const advance = (session_id: string, signal: "next" | "skip" = "next", node_id?: string) =>
  post(`/session/${session_id}/advance`, { signal, node_id });

export const jump = (session_id: string, node_id: string) =>
  post(`/session/${session_id}/jump`, { node_id });

export const retry = (session_id: string, node_id?: string) =>
  post<{ current_node_id: string; inserted: boolean }>(`/session/${session_id}/retry`, { node_id });

// --- File viewer ---

export interface FileContent {
  path: string;
  content: string;
}

export const getFile = (session_id: string, path: string) =>
  get<FileContent>(`/session/${session_id}/file?path=${encodeURIComponent(path)}`);
