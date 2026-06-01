const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// --- Goal dialogue ---

export interface Question {
  text: string;
  options: string[] | null;
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

export const sessionStart = (repo_url: string, goal: Record<string, string>) =>
  post<SessionStartResponse>("/session/start", { repo_url, goal });

// --- Learning graph ---

export type UnderstandingState = "not_started" | "partial" | "understood";

export interface GraphNode {
  id: string;
  title: string;
  file: string;
  line_start: number;
  line_end: number;
  understanding_state: UnderstandingState;
  visited: boolean;
}

export interface GraphEdge {
  from_id: string;
  to_id: string;
  kind: string;
}

export interface SessionGraph {
  session_id: string;
  current_node_id: string | null;
  nodes: GraphNode[];
  edges: GraphEdge[];
  readiness: number; // 0.0 – 1.0
}

export const getSession = (session_id: string) =>
  get<SessionGraph>(`/session/${session_id}`);

// --- Lesson ---

export interface LessonBody {
  walkthrough: string;
  prompt: string;
  prompt_kind: string;
}

export interface Lesson {
  node_id: string;
  lesson: LessonBody;
}

export const getLesson = (session_id: string) =>
  get<Lesson>(`/session/${session_id}/lesson`);

// --- Respond ---

export interface RespondResult {
  classification: "understood" | "partial" | "confused" | "off-topic";
  rationale: string;
  understanding_state: string;
}

export const respond = (session_id: string, answer: string, node_id?: string) =>
  post<RespondResult>(`/session/${session_id}/respond`, { response: answer, node_id });

// --- Advance ---

export const advance = (session_id: string, signal: "next" | "skip" = "next", node_id?: string) =>
  post(`/session/${session_id}/advance`, { signal, node_id });

export const jump = (session_id: string, node_id: string) =>
  post(`/session/${session_id}/jump`, { node_id });

// --- File viewer ---

export interface FileContent {
  path: string;
  content: string;
}

export const getFile = (session_id: string, path: string) =>
  get<FileContent>(`/session/${session_id}/file?path=${encodeURIComponent(path)}`);
