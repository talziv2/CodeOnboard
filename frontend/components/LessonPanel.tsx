"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import MapView from "@/components/MapView";
import { getLesson, respond, advance, retry } from "@/lib/api";
import type {
  Attempt, Classification, GraphNode, Lesson, RespondResult, SessionGraph,
} from "@/lib/api";
import { tagStyle } from "@/lib/tags";

interface Props {
  sessionId: string;
  nodeId: string;
  node: GraphNode;
  position: number;
  total: number;
  isPrerequisite: boolean;
  graph: SessionGraph;
  onFileClick: (file: string) => void;
  onAdvance: () => Promise<void>;
  onRespond: () => void;
  onFinish: () => void;
}

const VERDICT: Record<string, { label: string; color: string }> = {
  understood: { label: "Understood", color: "#4fb286" },
  partial: { label: "Partly there", color: "#d9a441" },
  confused: { label: "Not yet", color: "#d4634f" },
  "off-topic": { label: "Off topic", color: "#d4634f" },
};

const FAILED: Classification[] = ["confused", "off-topic"];

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
        {children}
      </span>
      <span aria-hidden className="h-px flex-1 bg-rule" />
    </div>
  );
}

function whenLabel(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return new Date(iso).toLocaleDateString();
}

/** One graded answer, collapsed to its verdict until opened. */
function AttemptCard({ attempt, index }: { attempt: Attempt; index: number }) {
  const verdict = VERDICT[attempt.classification] ?? {
    label: attempt.classification,
    color: "#dde5ea",
  };
  return (
    <details className="group rounded border border-rule bg-slab open:bg-trench">
      <summary className="flex cursor-pointer list-none items-center gap-2.5 px-3 py-2">
        <span aria-hidden className="font-mono text-[10px] text-graphite">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span
          className="font-mono text-[10.5px] uppercase tracking-[0.13em]"
          style={{ color: verdict.color }}
        >
          {verdict.label}
        </span>
        <span className="ml-auto font-mono text-[10px] text-graphite">
          {whenLabel(attempt.at)}
        </span>
        <span
          aria-hidden
          className="font-mono text-[10px] text-graphite transition group-open:rotate-90"
        >
          ›
        </span>
      </summary>
      <div className="flex flex-col gap-2.5 border-t border-rule px-3 py-3">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-graphite">
            You wrote
          </span>
          <p className="measure whitespace-pre-wrap text-[12.5px] leading-relaxed text-paper">
            {attempt.answer}
          </p>
        </div>
        {attempt.rationale && (
          <div className="flex flex-col gap-1">
            <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-graphite">
              Feedback
            </span>
            <p className="measure text-[12.5px] leading-relaxed text-graphite">
              {attempt.rationale}
            </p>
          </div>
        )}
      </div>
    </details>
  );
}

export default function LessonPanel({
  sessionId, nodeId, node, position, total, isPrerequisite,
  graph, onFileClick, onAdvance, onRespond, onFinish,
}: Props) {
  const router = useRouter();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<RespondResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    setLesson(null);
    setResult(null);
    setAnswer("");
    setError(null);
    setLoading(true);
    getLesson(sessionId)
      .then(setLesson)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [sessionId, nodeId]);

  const submitAnswer = async () => {
    if (!answer.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await respond(sessionId, answer, nodeId);
      setResult(res);
      // A warm-up moves the session pointer, and refreshing now would swap this
      // panel out before the verdict could be read. Follow on the user's click.
      if (res.mutation?.kind !== "prerequisite") onRespond();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Couldn't grade that answer. Try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleAdvance = async () => {
    setLoading(true);
    try {
      const res = (await advance(sessionId, "next", nodeId)) as { done?: boolean };
      await onAdvance();
      if (res?.done) setDone(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Couldn't move to the next stop.");
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async () => {
    setLoading(true);
    try {
      await retry(sessionId, nodeId);
      setResult(null);
      setAnswer("");
      await onAdvance();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Couldn't build a warm-up for this one.");
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return <CompletionScreen graph={graph} onNewSession={() => router.push("/")} onFinish={onFinish} />;
  }

  if (loading && !lesson) {
    return (
      <p className="animate-pulse font-mono text-sm text-graphite">Writing this lesson…</p>
    );
  }

  if (error && !lesson) {
    return <p className="text-sm text-rust">{error}</p>;
  }

  if (!lesson) return null;

  // A warm-up was spliced in before this node, so its lesson is the thing that
  // was meant to unblock this one.
  const warmUpEdge = graph.edges.find(
    (e) => e.kind === "prerequisite" && e.to_id === nodeId
  );
  const warmUpTitle = warmUpEdge
    ? graph.nodes.find((n) => n.id === warmUpEdge.from_id)?.title ?? null
    : null;

  // When a warm-up is auto-created we skip the graph refresh so the verdict
  // stays readable, which leaves node.attempts one behind. Show the answer that
  // was just graded anyway — it can't double up, because in that branch the
  // refresh that would have carried it never ran.
  const recorded = node.attempts ?? [];
  const pending: Attempt | null =
    result && result.mutation?.kind === "prerequisite"
      ? {
          answer,
          classification: result.classification,
          rationale: result.rationale,
          at: new Date().toISOString(),
        }
      : null;
  const attempts = pending ? [...recorded, pending] : recorded;
  const latest = attempts[attempts.length - 1];
  const recovered =
    warmUpTitle !== null &&
    attempts.some((a) => FAILED.includes(a.classification)) &&
    latest?.classification === "understood";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-graphite">
          {isPrerequisite ? "Warm-up · added after confusion" : `Stop ${position} of ${total}`}
        </span>

        <h2 className="font-display text-[23px] font-medium leading-[1.2] tracking-tight text-chalk text-balance">
          {node.title}
        </h2>

        <button
          onClick={() => onFileClick(node.file)}
          className="w-fit border-b border-dashed border-signal-dim pb-px font-mono text-[11px] text-signal transition hover:border-signal"
        >
          {node.file} · lines {node.line_start}–{node.line_end}
        </button>

        {node.concept_tags.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1.5">
            {node.concept_tags.map((tag) => {
              const s = tagStyle(tag);
              return (
                <span
                  key={tag}
                  className="rounded-[2px] border px-1.5 py-px font-mono text-[9.5px] tracking-[0.05em]"
                  style={{ color: s.text, borderColor: s.border, background: s.background }}
                >
                  {s.label}
                </span>
              );
            })}
          </div>
        )}
      </div>

      {recovered && (
        <div className="flex flex-col gap-1 rounded border border-jade/40 bg-jade/10 px-4 py-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-jade">
            The warm-up worked
          </span>
          <p className="text-[12.5px] leading-relaxed text-paper">
            You got this one after studying{" "}
            <span className="text-chalk">“{warmUpTitle}”</span> first. It stays marked
            as a rough patch, but you came back from it.
          </p>
        </div>
      )}

      <div className="flex flex-col gap-3">
        <SectionLabel>Walkthrough</SectionLabel>
        <p className="measure whitespace-pre-wrap text-[13.5px] leading-[1.72] text-paper">
          {lesson.lesson.walkthrough}
        </p>
      </div>

      {attempts.length > 0 && (
        <div className="flex flex-col gap-3">
          <SectionLabel>
            Your answers ({attempts.length})
          </SectionLabel>
          <div className="flex flex-col gap-2">
            {attempts.map((attempt, i) => (
              <AttemptCard key={`${attempt.at}-${i}`} attempt={attempt} index={i} />
            ))}
          </div>
        </div>
      )}

      {!result && (
        <div className="flex flex-col gap-3">
          <SectionLabel>Check your understanding</SectionLabel>
          <p className="measure text-[13.5px] leading-[1.6] text-chalk">{lesson.lesson.prompt}</p>
          <textarea
            rows={4}
            className="w-full resize-none rounded border border-rule bg-trench p-3 text-[13px] text-chalk placeholder:text-graphite focus:border-signal-dim focus:outline-none"
            placeholder="Write your answer…"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                submitAnswer();
              }
            }}
            disabled={loading}
          />
          {error && <p className="text-sm text-rust">{error}</p>}
          <div className="flex items-center gap-3">
            <button
              onClick={submitAnswer}
              disabled={loading || !answer.trim()}
              className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[13px] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
            >
              {loading ? "Grading…" : "Submit"}
            </button>
            <button
              onClick={handleAdvance}
              disabled={loading}
              className="rounded border border-rule px-4 py-2 text-[13px] text-graphite transition hover:border-signal-dim hover:text-signal disabled:opacity-40"
            >
              Skip this stop
            </button>
            <span className="ml-auto font-mono text-[10.5px] text-graphite">⌘↵ to submit</span>
          </div>
        </div>
      )}

      {result && (
        <div className="flex flex-col gap-3 rounded border border-rule bg-slab p-4">
          <p
            className="font-mono text-[11px] uppercase tracking-[0.14em]"
            style={{ color: VERDICT[result.classification]?.color ?? "#dde5ea" }}
          >
            {VERDICT[result.classification]?.label ?? result.classification}
          </p>
          <p className="measure text-[13px] leading-[1.65] text-paper">{result.rationale}</p>
          {error && <p className="text-sm text-rust">{error}</p>}

          {FAILED.includes(result.classification) && (
            <p className="text-[12.5px] leading-relaxed text-paper">
              {result.mutation?.kind === "prerequisite"
                ? "We've added a shorter warm-up before this stop to build up to it."
                : result.mutation?.reason === "prerequisite_exists"
                ? "You've already had a warm-up for this stop, so there isn't another one to add."
                : "We couldn't build a warm-up for this one, so it's your call how to continue."}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3">
            {result.classification === "understood" && (
              <button
                onClick={handleAdvance}
                disabled={loading}
                className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[13px] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
              >
                {loading ? "Loading…" : "Next stop →"}
              </button>
            )}

            {/* Partly there: moving on is the default, a warm-up is on offer. */}
            {result.classification === "partial" && (
              <>
                <button
                  onClick={handleAdvance}
                  disabled={loading}
                  className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[13px] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
                >
                  {loading ? "Loading…" : "Next stop →"}
                </button>
                <button
                  onClick={handleRetry}
                  disabled={loading}
                  className="rounded border border-rule px-4 py-2 text-[13px] text-graphite transition hover:border-signal-dim hover:text-signal disabled:opacity-40"
                >
                  Build me a warm-up
                </button>
              </>
            )}

            {FAILED.includes(result.classification) && (
              <>
                {result.mutation?.kind === "prerequisite" && (
                  <button
                    onClick={async () => {
                      setLoading(true);
                      try {
                        await onAdvance();
                      } finally {
                        setLoading(false);
                      }
                    }}
                    disabled={loading}
                    className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[13px] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
                  >
                    {loading ? "Loading…" : "Start the warm-up →"}
                  </button>
                )}
                <button
                  onClick={handleAdvance}
                  disabled={loading}
                  className="rounded border border-rule px-4 py-2 text-[13px] text-graphite transition hover:border-signal-dim hover:text-signal disabled:opacity-40"
                >
                  {result.mutation?.kind === "prerequisite"
                    ? "Skip it, move on"
                    : "Move on anyway"}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      <div className="border-t border-rule pt-4">
        <button
          onClick={() => setDone(true)}
          className="font-mono text-[10.5px] text-graphite transition hover:text-chalk"
        >
          Finish session early
        </button>
      </div>
    </div>
  );
}

// ── Completion ───────────────────────────────────────────────────────────────

function CompletionScreen({
  graph, onNewSession, onFinish,
}: { graph: SessionGraph; onNewSession: () => void; onFinish: () => void }) {
  const [tab, setTab] = useState<"summary" | "map">("summary");
  const weak = graph.nodes.filter((n) => n.weak_spot);
  const understood = graph.nodes.filter((n) => n.understanding_state === "understood").length;

  return (
    <div className="flex h-full flex-col gap-5">
      <div className="flex shrink-0 gap-1 border-b border-rule">
        {(["summary", "map"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.12em] transition ${
              tab === t
                ? "border-signal text-signal"
                : "border-transparent text-graphite hover:text-chalk"
            }`}
          >
            {t === "map" ? "Your map" : "Summary"}
          </button>
        ))}
      </div>

      {tab === "summary" ? (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-graphite">
              Session complete
            </span>
            <h2 className="font-display text-[26px] font-medium leading-tight tracking-tight text-chalk">
              You understood {understood} of {graph.nodes.length} concepts
            </h2>
            <p className="measure text-[13.5px] leading-[1.7] text-paper">
              Your map is saved. Come back to this repo and goal and you'll pick up
              exactly where you left off — including the stops still marked weak.
            </p>
          </div>

          {weak.length > 0 && (
            <div className="flex flex-col gap-3 rounded border border-rule bg-slab p-4">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-rust">
                Worth another pass ({weak.length})
              </span>
              <ul className="flex flex-col gap-2.5">
                {weak.map((n) => (
                  <li key={n.id} className="flex flex-col gap-0.5">
                    <span className="text-[13px] font-medium text-chalk">{n.title}</span>
                    <span className="font-mono text-[10.5px] text-graphite">
                      {n.file} · lines {n.line_start}–{n.line_end}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={onNewSession}
              className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[13px] font-medium text-signal transition hover:bg-signal/25"
            >
              Start a new session
            </button>
            <button
              onClick={onFinish}
              className="rounded border border-rule px-4 py-2 text-[13px] text-graphite transition hover:border-signal-dim hover:text-signal"
            >
              Go home
            </button>
          </div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-hidden rounded border border-rule">
          <MapView
            nodes={graph.nodes}
            edges={graph.edges}
            currentNodeId={graph.current_node_id}
            readiness={graph.readiness}
            repoUrl={graph.repo_url}
            onNodeClick={() => {}}
          />
        </div>
      )}
    </div>
  );
}
