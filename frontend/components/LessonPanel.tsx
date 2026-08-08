"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import MapView from "@/components/MapView";
import { getLesson, respond, advance, retry } from "@/lib/api";
import type {
  Attempt, Classification, GraphNode, Lesson, RespondResult, SessionGraph,
} from "@/lib/api";
import type { Dictionary } from "@/lib/i18n";
import { tagStyle, tagLabel } from "@/lib/tags";
import { useI18n } from "@/lib/i18n/context";

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

/** Classification keys stay English on the wire; only the label is localized. */
const VERDICT_COLOR: Record<string, string> = {
  understood: "#4fb286",
  partial: "#d9a441",
  confused: "#d4634f",
  "off-topic": "#d4634f",
};

const NEUTRAL = "#dde5ea";

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

/** Chevron that points along the reading direction when closed, down when open. */
function Chevron() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 10 10"
      className="h-2.5 w-2.5 shrink-0 fill-none stroke-graphite stroke-[1.5] transition-transform group-open:rotate-90 rtl:rotate-180 rtl:group-open:rotate-90"
    >
      <path d="M3.5 1.5 L7 5 L3.5 8.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function whenLabel(t: Dictionary, iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return t.lesson.when.justNow;
  if (mins < 60) return t.lesson.when.minutes(mins);
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return t.lesson.when.hours(hrs);
  return new Date(iso).toLocaleDateString();
}

/** One graded answer, collapsed to its verdict until opened. */
function AttemptCard({ attempt, index }: { attempt: Attempt; index: number }) {
  const { t } = useI18n();
  const label = t.lesson.verdict[attempt.classification] ?? attempt.classification;
  const color = VERDICT_COLOR[attempt.classification] ?? NEUTRAL;

  return (
    <details className="group rounded border border-rule bg-slab open:bg-trench">
      <summary className="flex cursor-pointer list-none items-center gap-2.5 px-3 py-2">
        <span aria-hidden dir="ltr" className="font-mono text-[10px] text-graphite">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span
          className="font-mono text-[10.5px] uppercase tracking-[0.13em]"
          style={{ color }}
        >
          {label}
        </span>
        <span className="ms-auto font-mono text-[10px] text-graphite">
          {whenLabel(t, attempt.at)}
        </span>
        <Chevron />
      </summary>
      <div className="flex flex-col gap-2.5 border-t border-rule px-3 py-3">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-graphite">
            {t.lesson.youWrote}
          </span>
          <p className="measure bidi-auto whitespace-pre-wrap text-[12.5px] leading-relaxed text-paper">
            {attempt.answer}
          </p>
        </div>
        {attempt.rationale && (
          <div className="flex flex-col gap-1">
            <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-graphite">
              {t.lesson.feedback}
            </span>
            <p className="measure bidi-auto text-[12.5px] leading-relaxed text-graphite">
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
  const { t, te, locale } = useI18n();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<RespondResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // Refetching on a locale change is the point: the server returns this
  // lesson translated into the new language. The verdict is deliberately not
  // cleared — a switch mid-answer shouldn't discard feedback already earned.
  useEffect(() => {
    setLesson(null);
    setError(null);
    setLoading(true);
    getLesson(sessionId, locale)
      .then(setLesson)
      .catch((e) => setError(te(e.message)))
      .finally(() => setLoading(false));
    // `te` is a fresh closure on every provider render; `locale` is the part
    // of it that actually matters here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, nodeId, locale]);

  // Moving to a different node is what clears the answer in progress.
  useEffect(() => {
    setResult(null);
    setAnswer("");
  }, [sessionId, nodeId]);

  const submitAnswer = async () => {
    if (!answer.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await respond(sessionId, answer, nodeId, locale);
      setResult(res);
      // A warm-up moves the session pointer, and refreshing now would swap this
      // panel out before the verdict could be read. Follow on the user's click.
      if (res.mutation?.kind !== "prerequisite") onRespond();
    } catch (e: unknown) {
      setError(e instanceof Error ? te(e.message) : t.lesson.gradeFailed);
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
      setError(e instanceof Error ? te(e.message) : t.lesson.advanceFailed);
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
      setError(e instanceof Error ? te(e.message) : t.lesson.warmUpFailed);
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return <CompletionScreen graph={graph} onNewSession={() => router.push("/")} onFinish={onFinish} />;
  }

  if (loading && !lesson) {
    return (
      <p className="animate-pulse font-mono text-sm text-graphite">{t.lesson.writing}</p>
    );
  }

  if (error && !lesson) {
    return <p className="bidi-auto text-sm text-rust">{error}</p>;
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
          {isPrerequisite ? t.lesson.warmUpHeading : t.lesson.stopOf(position, total)}
        </span>

        <h2 className="font-display text-[23px] font-medium leading-[1.2] tracking-tight text-chalk text-balance">
          {node.title}
        </h2>

        <button
          onClick={() => onFileClick(node.file)}
          className="w-fit border-b border-dashed border-signal-dim pb-px font-mono text-[11px] text-signal transition hover:border-signal"
        >
          <span dir="ltr">{node.file}</span>
          {" · "}
          {t.lesson.lines(node.line_start, node.line_end)}
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
                  {tagLabel(t, tag)}
                </span>
              );
            })}
          </div>
        )}
      </div>

      {recovered && (
        <div className="flex flex-col gap-1 rounded border border-jade/40 bg-jade/10 px-4 py-3">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-jade">
            {t.lesson.recoveredLabel}
          </span>
          <p className="text-[12.5px] leading-relaxed text-paper">
            {t.lesson.recoveredBody}{" "}
            <span className="text-chalk">“{warmUpTitle}”</span>
            {t.lesson.recoveredBodyEnd}
          </p>
        </div>
      )}

      <div className="flex flex-col gap-3">
        <SectionLabel>{t.lesson.walkthrough}</SectionLabel>
        {/* Agent prose interleaves the user's language with code identifiers,
            so direction is resolved line by line rather than for the block. */}
        <p className="measure bidi-auto whitespace-pre-wrap text-[13.5px] leading-[1.72] text-paper">
          {lesson.lesson.walkthrough}
        </p>
      </div>

      {attempts.length > 0 && (
        <div className="flex flex-col gap-3">
          <SectionLabel>{t.lesson.yourAnswers(attempts.length)}</SectionLabel>
          <div className="flex flex-col gap-2">
            {attempts.map((attempt, i) => (
              <AttemptCard key={`${attempt.at}-${i}`} attempt={attempt} index={i} />
            ))}
          </div>
        </div>
      )}

      {!result && (
        <div className="flex flex-col gap-3">
          <SectionLabel>{t.lesson.checkUnderstanding}</SectionLabel>
          <p className="measure bidi-auto text-[13.5px] leading-[1.6] text-chalk">
            {lesson.lesson.prompt}
          </p>
          <textarea
            rows={4}
            className="w-full resize-none rounded border border-rule bg-trench p-3 text-start text-[13px] text-chalk placeholder:text-graphite focus:border-signal-dim focus:outline-none"
            placeholder={t.lesson.answerPlaceholder}
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
          {error && <p className="bidi-auto text-sm text-rust">{error}</p>}
          <div className="flex items-center gap-3">
            <button
              onClick={submitAnswer}
              disabled={loading || !answer.trim()}
              className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[13px] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
            >
              {loading ? t.lesson.grading : t.lesson.submit}
            </button>
            <button
              onClick={handleAdvance}
              disabled={loading}
              className="rounded border border-rule px-4 py-2 text-[13px] text-graphite transition hover:border-signal-dim hover:text-signal disabled:opacity-40"
            >
              {t.lesson.skipStop}
            </button>
            <span className="ms-auto font-mono text-[10.5px] text-graphite">
              {t.lesson.submitHint}
            </span>
          </div>
        </div>
      )}

      {result && (
        <div className="flex flex-col gap-3 rounded border border-rule bg-slab p-4">
          <p
            className="font-mono text-[11px] uppercase tracking-[0.14em]"
            style={{ color: VERDICT_COLOR[result.classification] ?? NEUTRAL }}
          >
            {t.lesson.verdict[result.classification] ?? result.classification}
          </p>
          <p className="measure bidi-auto text-[13px] leading-[1.65] text-paper">
            {result.rationale}
          </p>
          {error && <p className="bidi-auto text-sm text-rust">{error}</p>}

          {FAILED.includes(result.classification) && (
            <p className="text-[12.5px] leading-relaxed text-paper">
              {result.mutation?.kind === "prerequisite"
                ? t.lesson.warmUpAdded
                : result.mutation?.reason === "prerequisite_exists"
                ? t.lesson.warmUpExists
                : t.lesson.warmUpUnavailable}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3">
            {result.classification === "understood" && (
              <button
                onClick={handleAdvance}
                disabled={loading}
                className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[13px] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
              >
                {loading ? t.lesson.loadingShort : t.lesson.nextStop}
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
                  {loading ? t.lesson.loadingShort : t.lesson.nextStop}
                </button>
                <button
                  onClick={handleRetry}
                  disabled={loading}
                  className="rounded border border-rule px-4 py-2 text-[13px] text-graphite transition hover:border-signal-dim hover:text-signal disabled:opacity-40"
                >
                  {t.lesson.buildWarmUp}
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
                    {loading ? t.lesson.loadingShort : t.lesson.startWarmUp}
                  </button>
                )}
                <button
                  onClick={handleAdvance}
                  disabled={loading}
                  className="rounded border border-rule px-4 py-2 text-[13px] text-graphite transition hover:border-signal-dim hover:text-signal disabled:opacity-40"
                >
                  {result.mutation?.kind === "prerequisite"
                    ? t.lesson.skipItMoveOn
                    : t.lesson.moveOnAnyway}
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
          {t.lesson.finishEarly}
        </button>
      </div>
    </div>
  );
}

// ── Completion ───────────────────────────────────────────────────────────────

function CompletionScreen({
  graph, onNewSession, onFinish,
}: { graph: SessionGraph; onNewSession: () => void; onFinish: () => void }) {
  const { t } = useI18n();
  const [tab, setTab] = useState<"summary" | "map">("summary");
  const weak = graph.nodes.filter((n) => n.weak_spot);
  const understood = graph.nodes.filter((n) => n.understanding_state === "understood").length;

  return (
    <div className="flex h-full flex-col gap-5">
      <div className="flex shrink-0 gap-1 border-b border-rule">
        {(["summary", "map"] as const).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2 font-mono text-[11px] uppercase tracking-[0.12em] transition ${
              tab === key
                ? "border-signal text-signal"
                : "border-transparent text-graphite hover:text-chalk"
            }`}
          >
            {key === "map" ? t.completion.tabMap : t.completion.tabSummary}
          </button>
        ))}
      </div>

      {tab === "summary" ? (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-graphite">
              {t.completion.label}
            </span>
            <h2 className="font-display text-[26px] font-medium leading-tight tracking-tight text-chalk">
              {t.completion.heading(understood, graph.nodes.length)}
            </h2>
            <p className="measure text-[13.5px] leading-[1.7] text-paper">
              {t.completion.body}
            </p>
          </div>

          {weak.length > 0 && (
            <div className="flex flex-col gap-3 rounded border border-rule bg-slab p-4">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-rust">
                {t.completion.anotherPass(weak.length)}
              </span>
              <ul className="flex flex-col gap-2.5">
                {weak.map((n) => (
                  <li key={n.id} className="flex flex-col gap-0.5">
                    <span className="text-[13px] font-medium text-chalk">{n.title}</span>
                    <span className="font-mono text-[10.5px] text-graphite">
                      <span dir="ltr">{n.file}</span>
                      {" · "}
                      {t.lesson.lines(n.line_start, n.line_end)}
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
              {t.completion.newSession}
            </button>
            <button
              onClick={onFinish}
              className="rounded border border-rule px-4 py-2 text-[13px] text-graphite transition hover:border-signal-dim hover:text-signal"
            >
              {t.completion.goHome}
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
