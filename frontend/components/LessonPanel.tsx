"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import MapView from "@/components/MapView";
import { getLesson, respond, advance, retry } from "@/lib/api";
import type {
  Anchor, Attempt, Classification, GraphNode, Lesson, RespondResult, SessionGraph,
} from "@/lib/api";
import { tagStyle, tagLabel } from "@/lib/tags";
import { errorText, t } from "@/lib/strings";

interface Props {
  sessionId: string;
  nodeId: string;
  node: GraphNode;
  position: number;
  total: number;
  isPrerequisite: boolean;
  graph: SessionGraph;
  /** A range is passed for multi-anchor units so the pane highlights THAT step. */
  onFileClick: (file: string, lineStart?: number, lineEnd?: number) => void;
  onAdvance: () => Promise<void>;
  onRespond: () => void;
  onFinish: () => void;
}

/** Keyed by the classification value the Grader returns. */
const VERDICT_COLOR: Record<string, string> = {
  understood: "var(--color-jade)",
  partial: "var(--color-brass)",
  confused: "var(--color-rust)",
  "off-topic": "var(--color-rust)",
};

const NEUTRAL = "var(--color-chalk)";

const FAILED: Classification[] = ["confused", "off-topic"];

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.16em] text-graphite">
        {children}
      </span>
      <span aria-hidden className="h-px flex-1 bg-rule" />
    </div>
  );
}

/** Chevron that points right when closed, down when open. */
function Chevron() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 10 10"
      className="h-2.5 w-2.5 shrink-0 fill-none stroke-graphite stroke-[1.5] transition-transform group-open:rotate-90"
    >
      <path d="M3.5 1.5 L7 5 L3.5 8.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function whenLabel(iso: string): string {
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
  const label = t.lesson.verdict[attempt.classification] ?? attempt.classification;
  const color = VERDICT_COLOR[attempt.classification] ?? NEUTRAL;

  return (
    <details className="group rounded border border-rule bg-slab open:bg-trench">
      <summary className="flex cursor-pointer list-none items-center gap-2.5 px-3 py-2">
        <span aria-hidden className="font-mono text-[calc(10rem/16)] text-graphite">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span
          className="font-mono text-[calc(10.5rem/16)] uppercase tracking-[0.13em]"
          style={{ color }}
        >
          {label}
        </span>
        <span className="ms-auto font-mono text-[calc(10rem/16)] text-graphite">
          {whenLabel(attempt.at)}
        </span>
        <Chevron />
      </summary>
      <div className="flex flex-col gap-2.5 border-t border-rule px-3 py-3">
        <div className="flex flex-col gap-1">
          <span className="font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.14em] text-graphite">
            {t.lesson.youWrote}
          </span>
          <p className="measure whitespace-pre-wrap text-[calc(12.5rem/16)] leading-relaxed text-paper">
            {attempt.answer}
          </p>
        </div>
        {attempt.rationale && (
          <div className="flex flex-col gap-1">
            <span className="font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.14em] text-graphite">
              {t.lesson.feedback}
            </span>
            <p className="measure text-[calc(12.5rem/16)] leading-relaxed text-graphite">
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
    setError(null);
    setLoading(true);
    getLesson(sessionId)
      .then(setLesson)
      .catch((e) => setError(errorText(e.message)))
      .finally(() => setLoading(false));
  }, [sessionId, nodeId]);

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
      const res = await respond(sessionId, answer, nodeId);
      setResult(res);
      // A re-teach replaced the cached lesson with one that names the
      // misconception. Pull it, so what is on screen is the corrected lesson
      // rather than the one that misled them.
      if (res.adaptation?.retaught) {
        getLesson(sessionId).then(setLesson).catch(() => {});
      }
      // A warm-up moves the session pointer, and refreshing now would swap this
      // panel out before the verdict could be read. Follow on the user's click.
      if (res.mutation?.kind !== "prerequisite") onRespond();
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.lesson.gradeFailed);
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
      setError(e instanceof Error ? errorText(e.message) : t.lesson.advanceFailed);
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async () => {
    setLoading(true);
    try {
      const { inserted } = await retry(sessionId, nodeId);
      if (!inserted) {
        // Declining is a real answer — no candidate was a smaller foundation
        // than the stop they are on. Say so and leave the verdict panel up, so
        // the other ways forward stay reachable. Silently resetting the form
        // read as the button doing nothing, and this path became far easier to
        // reach once the offer stopped depending on the automatic action.
        setError(t.lesson.warmUpUnavailable);
        return;
      }
      setResult(null);
      setAnswer("");
      await onAdvance();
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.lesson.warmUpFailed);
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

  // A lesson written before the setup/reveal split has one body and nothing to
  // withhold. `setup` is what distinguishes the two — `walkthrough` is present
  // either way, because the backend assembles it for clients that only know it.
  const isSplit = Boolean(lesson.lesson.setup);

  // The explanation is withheld until the learner has committed to an answer —
  // that withholding IS the active-learning mechanism. It opens on a graded
  // answer, and also on a REVISIT: someone returning to a node they already
  // answered is reading, not being tested, and hiding it from them would be
  // pointless friction rather than pedagogy.
  const revealed = Boolean(result) || attempts.length > 0;

  const anchors: Anchor[] = node.anchors ?? [];
  const adaptation = result?.adaptation;
  // A hint, a follow-up or a corrected lesson is an invitation to answer again
  // — the node is still ahead of them, not behind them.
  const canAnswerAgain =
    adaptation !== undefined &&
    ["hint", "followup", "reteach"].includes(adaptation.kind);
  // Stepping back is the LEARNER's call, and it must not depend on the system
  // having independently chosen `prerequisite` (§18.11). That gating was
  // backwards: a `partial` learner could ask for a warm-up, while a `confused`
  // one whose gap was `wrong_model` — re-taught, not re-structured — could not.
  // The weaker grasp got fewer options. Offered wherever the objective was not
  // reached, except when a warm-up was just spliced in: the Mutator caps them at
  // one per node, so offering there would promise something it would decline.
  const warmUpInserted = result?.mutation?.kind === "prerequisite";
  const canRequestWarmUp =
    result !== null &&
    result?.classification !== "understood" &&
    !warmUpInserted;
  const recovered =
    warmUpTitle !== null &&
    attempts.some((a) => FAILED.includes(a.classification)) &&
    latest?.classification === "understood";

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <span className="font-mono text-[calc(10.5rem/16)] uppercase tracking-[0.14em] text-graphite">
          {isPrerequisite ? t.lesson.warmUpHeading : t.lesson.stopOf(position, total)}
        </span>

        <h2 className="font-display text-[calc(23rem/16)] font-medium leading-[1.2] tracking-tight text-chalk text-balance">
          {node.title}
        </h2>

        <button
          onClick={() => onFileClick(node.file)}
          className="w-fit border-b border-dashed border-signal-dim pb-px font-mono text-[calc(11rem/16)] text-signal transition hover:border-signal"
        >
          {node.file}
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
                  className="rounded-[2px] border px-1.5 py-px font-mono text-[calc(9.5rem/16)] tracking-[0.05em]"
                  style={{ color: s.text, borderColor: s.border, background: s.background }}
                >
                  {tagLabel(tag)}
                </span>
              );
            })}
          </div>
        )}
      </div>

      {recovered && (
        <div className="flex flex-col gap-1 rounded border border-jade/40 bg-jade/10 px-4 py-3">
          <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.14em] text-jade">
            {t.lesson.recoveredLabel}
          </span>
          <p className="text-[calc(12.5rem/16)] leading-relaxed text-paper">
            {t.lesson.recoveredBody}{" "}
            <span className="text-chalk">“{warmUpTitle}”</span>
            {t.lesson.recoveredBodyEnd}
          </p>
        </div>
      )}

      {isSplit && lesson.lesson.why_now && (
        <p className="measure border-s-2 border-rule ps-3 text-[calc(12.5rem/16)] italic leading-relaxed text-graphite">
          {lesson.lesson.why_now}
        </p>
      )}

      <div className="flex flex-col gap-3">
        {/* A pre-B4 lesson has no halves to withhold, so it renders exactly as
            it always did, under the label it always had. */}
        <SectionLabel>{isSplit ? t.lesson.setup : t.lesson.walkthrough}</SectionLabel>
        <p className="measure whitespace-pre-wrap text-[calc(13.5rem/16)] leading-[1.72] text-paper">
          {isSplit ? lesson.lesson.setup : lesson.lesson.walkthrough}
        </p>
      </div>

      {anchors.length > 1 && (
        <div className="flex flex-col gap-2">
          <SectionLabel>{t.lesson.tracePath}</SectionLabel>
          <ol className="flex flex-col gap-1">
            {anchors.map((a, i) => (
              <li key={`${a.file}-${a.line_start}-${i}`}>
                <button
                  onClick={() => onFileClick(a.file, a.line_start, a.line_end)}
                  className="group flex w-full items-baseline gap-2.5 rounded px-2 py-1 text-start transition hover:bg-slab"
                >
                  <span className="font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.13em] text-graphite">
                    {t.lesson.anchorStep(i + 1, anchors.length)}
                  </span>
                  <span className="min-w-0 flex-1 truncate font-mono text-[calc(11rem/16)] text-signal transition group-hover:text-chalk">
                    {a.symbol ?? a.file}
                  </span>
                  <span className="shrink-0 font-mono text-[calc(10rem/16)] text-graphite">
                    {t.lesson.lines(a.line_start, a.line_end)}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}

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
          <p className="measure text-[calc(13.5rem/16)] leading-[1.6] text-chalk">
            {lesson.lesson.prompt}
          </p>
          <textarea
            rows={4}
            className="w-full resize-none rounded border border-rule bg-trench p-3 text-start text-[calc(13rem/16)] text-chalk placeholder:text-graphite focus:border-signal-dim focus:outline-none"
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
          {error && <p className="text-sm text-rust">{error}</p>}
          <div className="flex items-center gap-3">
            <button
              onClick={submitAnswer}
              disabled={loading || !answer.trim()}
              className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[calc(13rem/16)] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
            >
              {loading ? t.lesson.grading : t.lesson.submit}
            </button>
            <button
              onClick={handleAdvance}
              disabled={loading}
              className="rounded border border-rule px-4 py-2 text-[calc(13rem/16)] text-graphite transition hover:border-signal-dim hover:text-signal disabled:opacity-40"
            >
              {t.lesson.skipStop}
            </button>
            <span className="ms-auto font-mono text-[calc(10.5rem/16)] text-graphite">
              {t.lesson.submitHint}
            </span>
          </div>
        </div>
      )}

      {/* The reveal. Held back until the learner has answered, which is the
          whole point of the split — then shown with the verdict rather than
          before it, so the explanation lands against what they actually said. */}
      {isSplit && revealed && lesson.lesson.reveal && (
        <div className="flex flex-col gap-3">
          <SectionLabel>{t.lesson.reveal}</SectionLabel>
          <p className="measure whitespace-pre-wrap text-[calc(13.5rem/16)] leading-[1.72] text-paper">
            {lesson.lesson.reveal}
          </p>

          {lesson.lesson.takeaway && (
            <div className="mt-1 flex flex-col gap-1.5 rounded border border-signal-dim/40 bg-signal/[0.06] px-4 py-3">
              <span className="font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.14em] text-signal">
                {t.lesson.takeaway}
              </span>
              <p className="measure text-[calc(13rem/16)] leading-[1.65] text-chalk">
                {lesson.lesson.takeaway}
              </p>
            </div>
          )}

          {lesson.lesson.ownership && (
            <div className="flex flex-col gap-1.5 rounded border border-rule bg-slab px-4 py-3">
              <span className="font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.14em] text-graphite">
                {t.lesson.ownership}
              </span>
              <p className="measure text-[calc(12.5rem/16)] leading-[1.65] text-paper">
                {lesson.lesson.ownership}
              </p>
            </div>
          )}
        </div>
      )}

      {result && (
        <div className="flex flex-col gap-3 rounded border border-rule bg-slab p-4">
          <p
            className="font-mono text-[calc(11rem/16)] uppercase tracking-[0.14em]"
            style={{ color: VERDICT_COLOR[result.classification] ?? NEUTRAL }}
          >
            {t.lesson.verdict[result.classification] ?? result.classification}
          </p>
          <p className="measure text-[calc(13rem/16)] leading-[1.65] text-paper">
            {result.rationale}
          </p>
          {error && <p className="text-sm text-rust">{error}</p>}

          {/* What the system did about the gap. Only a missing foundation
              grows the journey; the rest answer the learner where they are. */}
          {adaptation?.text && (
            <div className="flex flex-col gap-1.5 rounded border border-signal-dim/40 bg-signal/[0.06] px-4 py-3">
              <span className="font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.14em] text-signal">
                {adaptation.kind === "hint" ? t.lesson.hint : t.lesson.followup}
              </span>
              <p className="measure text-[calc(13rem/16)] leading-[1.65] text-chalk">
                {adaptation.text}
              </p>
            </div>
          )}

          {adaptation?.retaught && (
            <p className="font-mono text-[calc(10.5rem/16)] uppercase tracking-[0.13em] text-signal">
              {t.lesson.retaught}
            </p>
          )}

          {typeof adaptation?.pruned === "number" && adaptation.pruned > 0 && (
            <p className="font-mono text-[calc(10.5rem/16)] uppercase tracking-[0.13em] text-jade">
              {t.lesson.pruned(adaptation.pruned)}
            </p>
          )}

          {FAILED.includes(result.classification) &&
            adaptation?.kind === "prerequisite" && (
              <p className="text-[calc(12.5rem/16)] leading-relaxed text-paper">
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
                className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[calc(13rem/16)] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
              >
                {loading ? t.lesson.loadingShort : t.lesson.nextStop}
              </button>
            )}

            {/* Partly there: moving on is the default. The warm-up offer is
                shared with every other non-understood state, below. */}
            {result.classification === "partial" && (
              <button
                onClick={handleAdvance}
                disabled={loading}
                className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[calc(13rem/16)] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
              >
                {loading ? t.lesson.loadingShort : t.lesson.nextStop}
              </button>
            )}

            {canAnswerAgain && (
              <button
                onClick={() => { setResult(null); setAnswer(""); }}
                disabled={loading}
                className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[calc(13rem/16)] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
              >
                {t.lesson.tryAgain}
              </button>
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
                    className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[calc(13rem/16)] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
                  >
                    {loading ? t.lesson.loadingShort : t.lesson.startWarmUp}
                  </button>
                )}
                <button
                  onClick={handleAdvance}
                  disabled={loading}
                  className="rounded border border-rule px-4 py-2 text-[calc(13rem/16)] text-graphite transition hover:border-signal-dim hover:text-signal disabled:opacity-40"
                >
                  {result.mutation?.kind === "prerequisite"
                    ? t.lesson.skipItMoveOn
                    : t.lesson.moveOnAnyway}
                </button>
              </>
            )}

            {/* One offer, every state where the objective was not reached. */}
            {canRequestWarmUp && (
              <button
                onClick={handleRetry}
                disabled={loading}
                className="rounded border border-rule px-4 py-2 text-[calc(13rem/16)] text-graphite transition hover:border-signal-dim hover:text-signal disabled:opacity-40"
              >
                {t.lesson.buildWarmUp}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="border-t border-rule pt-4">
        <button
          onClick={() => setDone(true)}
          className="font-mono text-[calc(10.5rem/16)] text-graphite transition hover:text-chalk"
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
            className={`-mb-px border-b-2 px-4 py-2 font-mono text-[calc(11rem/16)] uppercase tracking-[0.12em] transition ${
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
            <span className="font-mono text-[calc(10.5rem/16)] uppercase tracking-[0.14em] text-graphite">
              {t.completion.label}
            </span>
            <h2 className="font-display text-[calc(26rem/16)] font-medium leading-tight tracking-tight text-chalk">
              {t.completion.heading(understood, graph.nodes.length)}
            </h2>
            <p className="measure text-[calc(13.5rem/16)] leading-[1.7] text-paper">
              {t.completion.body}
            </p>
          </div>

          {weak.length > 0 && (
            <div className="flex flex-col gap-3 rounded border border-rule bg-slab p-4">
              <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.14em] text-rust">
                {t.completion.anotherPass(weak.length)}
              </span>
              <ul className="flex flex-col gap-2.5">
                {weak.map((n) => (
                  <li key={n.id} className="flex flex-col gap-0.5">
                    <span className="text-[calc(13rem/16)] font-medium text-chalk">{n.title}</span>
                    <span className="font-mono text-[calc(10.5rem/16)] text-graphite">
                      {n.file}
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
              className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[calc(13rem/16)] font-medium text-signal transition hover:bg-signal/25"
            >
              {t.completion.newSession}
            </button>
            <button
              onClick={onFinish}
              className="rounded border border-rule px-4 py-2 text-[calc(13rem/16)] text-graphite transition hover:border-signal-dim hover:text-signal"
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
            progress={graph.progress}
            repoUrl={graph.repo_url}
            onNodeClick={() => {}}
          />
        </div>
      )}
    </div>
  );
}
