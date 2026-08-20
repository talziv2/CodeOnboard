"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import MapView from "@/components/MapView";
import {
  getLesson,
  respond,
  advance,
  retry,
  requestVerification,
  respondToVerification,
  waive,
} from "@/lib/api";
import type {
  Anchor, Attempt, Classification, GraphNode, Lesson, NodeGap, RespondResult,
  SessionGraph, VerificationPrompt,
} from "@/lib/api";
import Callout from "@/components/ui/Callout";
import AnswerComposer from "@/components/lesson/AnswerComposer";
import AttemptHistory from "@/components/lesson/AttemptHistory";
import GapList from "@/components/lesson/GapList";
import LessonBrief from "@/components/lesson/LessonBrief";
import SetupProse from "@/components/lesson/SetupProse";
import TracePath from "@/components/lesson/TracePath";
import VerificationBlock from "@/components/lesson/VerificationBlock";
import PracticeSurface from "@/components/ui/PracticeSurface";
import SectionLabel from "@/components/ui/SectionLabel";
import Button from "@/components/ui/Button";
import { lessonPhase } from "@/lib/lessonPhase";
import { NEUTRAL, VERDICT_COLOR } from "@/lib/verdict";
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
  /**
   * Whether the journey is over. Lifted out of this component because it is now
   * reachable from two places — the end of the walk, and `Finish session` in the
   * header menu — and a flag owned here could only be set from inside a lesson.
   */
  finished: boolean;
  /** End the journey: the walk ran out, or the learner chose to stop. */
  onFinish: () => void;
  /** Leave the session entirely, from the completion screen. */
  onLeave: () => void;
}

/**
 * The two classifications that count as not reaching the objective.
 *
 * Kept here rather than moved out with the colour table: this drives the warm-up
 * offer and the recovery test, which are the panel's decisions, not a renderer's.
 */
const FAILED: Classification[] = ["confused", "off-topic"];

export default function LessonPanel({
  sessionId, nodeId, node, position, total, isPrerequisite,
  graph, onFileClick, onAdvance, onRespond, finished, onFinish, onLeave,
}: Props) {
  const router = useRouter();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<RespondResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The outstanding verification question, once requested. Held in component
  // state rather than on the lesson: a verification is a different question with
  // a different lifetime, and `cached_lesson` is the teacher's artifact.
  const [verification, setVerification] = useState<VerificationPrompt | null>(null);
  const [verifying, setVerifying] = useState(false);

  const verdictRef = useRef<HTMLDivElement>(null);
  // What the last check was ABOUT, captured at submit time.
  //
  // Both halves are otherwise unrecoverable once the reply lands. The answer is
  // cleared from the composer and a verification attempt is deliberately kept
  // out of "Your answers", so without this the learner's own words vanish. And
  // `result.gaps` is the still-OPEN list, so a gap that just closed is by
  // definition absent from it — the claims have to come from the question that
  // targeted them.
  const [checked, setChecked] = useState<{ answer: string; targeted: NodeGap[] } | null>(null);

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
    setChecked(null);
  }, [sessionId, nodeId]);

  // Bring the verdict to the learner.
  //
  // INTERIM. Grading inserts the reveal ABOVE the verdict, so the verdict lands
  // roughly three viewports below the button that produced it — measured at
  // 2027px in a 611px column, with the scroll position unmoved. Until the
  // workspace co-locates an action with its own result, move the column and the
  // focus ring to the thing that just happened.
  //
  // Deliberately NOT `scrollIntoView`: measured against the real page it moved
  // nothing at all. There are two nested scroll contexts here — the lesson
  // column and the source pane — and it walks for its own.
  //
  // And deliberately NOT `offsetTop`, which is what the first attempt used and
  // why it still moved nothing: `offsetTop` is measured against the nearest
  // POSITIONED ancestor, and the lesson column is static, so the number belonged
  // to a different coordinate space than the one being scrolled. `CodeLines`
  // documents this same trap — its scroller is explicitly `relative` "so
  // offsetTop is measured against this box and not against the document".
  // Rect arithmetic needs no such cooperation from the layout.
  //
  // A third of the way down rather than centred, matching the source pane.
  useEffect(() => {
    const el = verdictRef.current;
    if (!result || !el) return;

    // Focus first: it must not depend on the scroll succeeding.
    el.focus({ preventScroll: true });

    let box: HTMLElement | null = el.parentElement;
    while (box && !/(auto|scroll)/.test(getComputedStyle(box).overflowY)) {
      box = box.parentElement;
    }
    if (!box) return;

    const delta = el.getBoundingClientRect().top - box.getBoundingClientRect().top;
    const top = Math.max(0, box.scrollTop + delta - box.clientHeight / 3);
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Plain assignment for the instant case rather than `scrollTo({behavior})`:
    // identical result, and it works where the animated form does not — a
    // backgrounded tab runs no animation frames, so `scrollTo` is inert there
    // while this is not.
    if (still) box.scrollTop = top;
    else box.scrollTo({ top, behavior: "smooth" });
  }, [result]);

  const submitAnswer = async () => {
    if (!answer.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await respond(sessionId, answer, nodeId);
      // A fresh assessment supersedes any check result on screen.
      setChecked(null);
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
      if (res?.done) onFinish();
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

  // Ask for a FRESH question about the leading gap. Not a retry: the learner
  // has already been shown the reasoning for the question they answered, so
  // re-asking it would test recall (§18.7).
  const onCheckUnderstanding = async () => {
    setVerifying(true);
    setError(null);
    try {
      setVerification(await requestVerification(sessionId, nodeId));
      setAnswer("");
      setResult(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.lesson.warmUpFailed);
    } finally {
      setVerifying(false);
    }
  };

  const onSubmitVerification = async () => {
    if (!answer.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const got = await respondToVerification(sessionId, answer, nodeId);
      // Captured BEFORE the composer and the prompt are cleared — see `checked`.
      setChecked({ answer, targeted: verification?.gaps ?? [] });
      setResult(got);
      setVerification(null);
      setAnswer("");
      onRespond();
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.lesson.warmUpFailed);
    } finally {
      setLoading(false);
    }
  };

  // Stop being asked. Never evidence — the stop stays short of demonstrated,
  // which is what keeps the measure honest while letting the journey finish.
  const onWaive = async (gapId?: string) => {
    setLoading(true);
    try {
      await waive(sessionId, gapId, nodeId);
      setVerification(null);
      onRespond();
    } catch (e: unknown) {
      setError(e instanceof Error ? errorText(e.message) : t.lesson.warmUpFailed);
    } finally {
      setLoading(false);
    }
  };

  if (finished) {
    return <CompletionScreen graph={graph} onNewSession={() => router.push("/")} onFinish={onLeave} />;
  }

  if (loading && !lesson) {
    return (
      <p className="animate-pulse font-mono text-aside text-graphite">{t.lesson.writing}</p>
    );
  }

  if (error && !lesson) {
    return <p className="text-aside text-rust">{error}</p>;
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
  // ASSESSMENTS only. "Your answers" is the record of attempts at the lesson's
  // own question; a verification answer replies to a different, gap-specific
  // question (gap-model M6) and carries no `classification`, so leaving it in
  // would render a blank row, inflate the count, and — worse — make `latest`
  // below refer to an answer about something else entirely.
  //
  // Filtered rather than labelled: showing verification answers in their own
  // right needs copy, and `strings.ts` is mid-change in another branch. That is
  // the frontend half of M9, not this.
  const recorded = (node.attempts ?? []).filter(
    (a) => (a.kind ?? "assessment") !== "verification"
  );
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

  // What the learner still does not know here, preferring the just-graded reply
  // over the graph, which lags by one refresh on the warm-up path.
  const openGaps: NodeGap[] = result?.gaps ?? node.gaps ?? [];

  // One region, three contents — the eyebrow is what says which.
  const practiceLabel = verification
    ? t.lesson.verificationHeading
    : result
      ? t.lesson.feedback
      : t.lesson.checkUnderstanding;

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

  // A CHECK, not an assessment. The backend deliberately returns
  // `classification: null` here — a verification answer is evidence about named
  // beliefs, not a re-grade of the objective — so every branch below that keys
  // off `classification` is silent on this path, and the panel has to read
  // `resolved` / `unresolved` instead.
  const isCheck = result?.kind === "verification";
  const closed = (checked?.targeted ?? []).filter((g) =>
    (result?.resolved ?? []).includes(g.id)
  );
  const stillOpen = (checked?.targeted ?? []).filter((g) =>
    (result?.unresolved ?? []).includes(g.id)
  );
  const checkOutcome =
    closed.length === 0
      ? { label: t.lesson.checkOpen, color: "var(--color-brass)" }
      : stillOpen.length === 0
      ? { label: t.lesson.checkCleared, color: "var(--color-jade)" }
      : { label: t.lesson.checkPartly, color: "var(--color-brass)" };

  const canRequestWarmUp =
    result !== null &&
    result?.classification !== "understood" &&
    !warmUpInserted &&
    // On a check, `classification` is null, so this test passed by accident and
    // "Build me a warm-up" became the ONLY button offered after a correct
    // answer. A warm-up is still reachable here, but as a fallback rather than
    // the whole response.
    !isCheck;
  const recovered =
    warmUpTitle !== null &&
    attempts.some((a) => FAILED.includes(a.classification)) &&
    latest?.classification === "understood";

  /**
   * What this lesson is doing, as one value — see `lib/lessonPhase.ts`.
   *
   * Nothing renders from it yet, deliberately: L1 introduces the concept with no
   * behaviour attached so the branch table can be checked against the UI that
   * already exists, before L4 starts keying rendering off it. The sixteen
   * conditionals below are untouched.
   */
  const phase = lessonPhase({ result, verification });

  return (
    // The one thing L1 renders: an invisible attribute, so a test can assert that
    // the derived phase agrees with the blocks actually on screen rather than
    // re-testing the pure function against itself. Zero visual diff, and it stays
    // useful as the hook L3 and L4's tests key off.
    <div className="flex flex-col gap-6" data-lesson-phase={phase}>
      <LessonBrief
        node={node}
        position={position}
        total={total}
        isPrerequisite={isPrerequisite}
        onFileClick={onFileClick}
      />

      {recovered && (
        <Callout tone="jade" label={t.lesson.recoveredLabel}>
          <p className="text-meta text-paper">
            {t.lesson.recoveredBody}{" "}
            <span className="text-chalk">“{warmUpTitle}”</span>
            {t.lesson.recoveredBodyEnd}
          </p>
        </Callout>
      )}

      {isSplit && lesson.lesson.why_now && (
        <p className="measure border-s-2 border-rule ps-3 text-meta italic text-graphite">
          {lesson.lesson.why_now}
        </p>
      )}

      <SetupProse
        isSplit={isSplit}
        body={isSplit ? lesson.lesson.setup : lesson.lesson.walkthrough}
      />

      {anchors.length > 1 && <TracePath anchors={anchors} onFileClick={onFileClick} />}

      {/* The outstanding-gaps list. §18.10 calls this "the product's most
          honest surface: it tells the learner what they still do not know, by
          name". Named rather than counted — a count says how much is wrong, and
          only the claim says what. */}
      {openGaps.length > 0 && (
        <GapList gaps={openGaps} onWaive={onWaive} disabled={loading} />
      )}

      {/* The verification question. No reveal and no model answer are rendered
          because none is sent — showing the answer beside the question is what
          made re-asking meaningless in the first place (§18.7). */}


      {attempts.length > 0 && <AttemptHistory attempts={attempts} />}

      {/* The lesson's own question. Hidden while a verification is outstanding:
          both blocks bind the SAME `answer` state, so rendering them together
          put two textareas on screen that mirrored each other's text, under two
          buttons both labelled "Submit" that did different things. `Not now`
          clears the verification and brings this back. */}
      <PracticeSurface label={practiceLabel}>
      {verification && (
        <VerificationBlock
          question={verification.question}
          answer={answer}
          onAnswerChange={setAnswer}
          onSubmit={onSubmitVerification}
          onDismiss={() => setVerification(null)}
          loading={loading}
        />
      )}
      {!result && !verification && (
        <AnswerComposer
          prompt={lesson.lesson.prompt}
          answer={answer}
          onAnswerChange={setAnswer}
          onSubmit={submitAnswer}
          onSkip={handleAdvance}
          loading={loading}
          error={error}
        />
      )}
      {result && (
        <div
          ref={verdictRef}
          // Focused after grading so the verdict is what a keyboard or screen
          // reader lands on, not just what the viewport moved to.
          tabIndex={-1}
          className="flex flex-col gap-3 rounded-card border border-rule bg-slab p-4"
        >
          <p
            className="font-mono text-micro uppercase tracking-[0.14em]"
            style={{
              color: isCheck
                ? checkOutcome.color
                : VERDICT_COLOR[result.classification] ?? NEUTRAL,
            }}
          >
            {isCheck
              ? checkOutcome.label
              : t.lesson.verdict[result.classification] ?? result.classification}
          </p>
          <p className="measure text-aside text-paper">
            {result.rationale}
          </p>

          {/* What the check actually did to the gap list, by name.
              `resolved` and `unresolved` were on the wire from the start and
              rendered nowhere, so a learner who answered correctly saw a card
              with an empty headline and no statement that anything had closed —
              while the gap silently disappeared from the list above. */}
          {isCheck && closed.length > 0 && (
            <Callout tone="jade" label={t.lesson.checkClosedLabel}>
              <ul className="flex flex-col gap-1">
                {closed.map((gap) => (
                  <li
                    key={gap.id}
                    className="measure text-meta text-paper line-through decoration-jade/60"
                  >
                    {gap.claim}
                  </li>
                ))}
              </ul>
            </Callout>
          )}

          {/* Deliberately NOT re-listing what is still open. The gap list above
              is already the authoritative, actionable copy of that, and naming
              them twice on one screen is the accumulation this redesign exists
              to remove. The card's job is what CHANGED — and a closed gap is the
              half that is otherwise unrecoverable, because it has left the list
              above by the time this renders. */}
          {isCheck && closed.length === 0 && (
            <p className="measure text-meta text-graphite">
              {t.lesson.checkNothingClosed}
            </p>
          )}

          {/* The learner's own words. A verification attempt is deliberately
              excluded from "Your answers" — it carries no classification, so
              including it would blank a row and corrupt `latest` — which left
              the answer nowhere at all once the composer cleared. */}
          {isCheck && checked?.answer && (
            <div className="flex flex-col gap-1">
              <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
                {t.lesson.youWrote}
              </span>
              <p className="measure whitespace-pre-wrap text-meta text-paper">
                {checked.answer}
              </p>
            </div>
          )}

          {error && <p className="text-aside text-rust">{error}</p>}

          {/* What the system did about the gap. Only a missing foundation
              grows the journey; the rest answer the learner where they are. */}
          {adaptation?.text && (
            <Callout
              tone="signal"
              label={adaptation.kind === "hint" ? t.lesson.hint : t.lesson.followup}
            >
              <p className="measure text-aside text-chalk">
                {adaptation.text}
              </p>
            </Callout>
          )}

          {adaptation?.retaught && (
            <p className="font-mono text-micro uppercase tracking-[0.13em] text-signal">
              {t.lesson.retaught}
            </p>
          )}

          {typeof adaptation?.pruned === "number" && adaptation.pruned > 0 && (
            <p className="font-mono text-micro uppercase tracking-[0.13em] text-jade">
              {t.lesson.pruned(adaptation.pruned)}
            </p>
          )}

          {FAILED.includes(result.classification) &&
            adaptation?.kind === "prerequisite" && (
              <p className="text-meta text-paper">
                {result.mutation?.kind === "prerequisite"
                  ? t.lesson.warmUpAdded
                  : result.mutation?.reason === "prerequisite_exists"
                  ? t.lesson.warmUpExists
                  : t.lesson.warmUpUnavailable}
              </p>
            )}

          <div className="flex flex-wrap items-center gap-3">
            {/* A check's own actions. Every branch below keys off
                `classification`, which is null here, so without this the only
                button reachable after a check was "Build me a warm-up" — offered
                because `null !== "understood"` happened to be true. The primary
                is whatever most directly closes what is left: another check
                while gaps remain, otherwise moving on. */}
            {isCheck && (
              <>
                {openGaps.length > 0 ? (
                  <Button variant="primary" size="md"
                    onClick={onCheckUnderstanding}
                    disabled={loading || verifying}
                  >
                    {verifying ? t.lesson.verifyCtaBusy : t.lesson.checkAnother}
                  </Button>
                ) : (
                  <Button variant="primary" size="md"
                    onClick={handleAdvance}
                    disabled={loading}
                  >
                    {loading ? t.lesson.loadingShort : t.lesson.nextStop}
                  </Button>
                )}
                {openGaps.length > 0 && (
                  <Button variant="secondary" size="md"
                    onClick={handleAdvance}
                    disabled={loading}
                  >
                    {loading ? t.lesson.loadingShort : t.lesson.nextStop}
                  </Button>
                )}
                {/* Still reachable when something is unresolved, but never the
                    whole response to a correct answer. */}
                {openGaps.length > 0 && !warmUpInserted && (
                  <Button variant="ghost"
                    onClick={handleRetry}
                    disabled={loading}
                  >
                    {t.lesson.buildWarmUp}
                  </Button>
                )}
              </>
            )}

            {result.classification === "understood" && (
              <Button variant="primary" size="md"
                onClick={handleAdvance}
                disabled={loading}
              >
                {loading ? t.lesson.loadingShort : t.lesson.nextStop}
              </Button>
            )}

            {/* Partly there: moving on is the default. The warm-up offer is
                shared with every other non-understood state, below. */}
            {result.classification === "partial" && (
              <Button variant="primary" size="md"
                onClick={handleAdvance}
                disabled={loading}
              >
                {loading ? t.lesson.loadingShort : t.lesson.nextStop}
              </Button>
            )}

            {canAnswerAgain && openGaps.length > 0 && (
              // NOT "Try again". That cleared the form and re-showed the very
              // question whose answer `reveal` had just given away, so passing it
              // proved only that they had read the page. This asks a NEW question
              // about the same misconception (§18.7).
              <Button variant="primary" size="md"
                onClick={onCheckUnderstanding}
                disabled={loading || verifying}
              >
                {verifying ? t.lesson.verifyCtaBusy : t.lesson.verifyCta}
              </Button>
            )}
            {canAnswerAgain && openGaps.length === 0 && (
              <Button variant="primary" size="md"
                onClick={() => { setResult(null); setAnswer(""); }}
                disabled={loading}
              >
                {t.lesson.tryAgain}
              </Button>
            )}

            {FAILED.includes(result.classification) && (
              <>
                {result.mutation?.kind === "prerequisite" && (
                  <Button variant="primary" size="md"
                    onClick={async () => {
                      setLoading(true);
                      try {
                        await onAdvance();
                      } finally {
                        setLoading(false);
                      }
                    }}
                    disabled={loading}
                  >
                    {loading ? t.lesson.loadingShort : t.lesson.startWarmUp}
                  </Button>
                )}
                <Button variant="secondary" size="md"
                  onClick={handleAdvance}
                  disabled={loading}
                >
                  {result.mutation?.kind === "prerequisite"
                    ? t.lesson.skipItMoveOn
                    : t.lesson.moveOnAnyway}
                </Button>
              </>
            )}

            {/* One offer, every state where the objective was not reached. */}
            {canRequestWarmUp && (
              <Button variant="secondary" size="md"
                onClick={handleRetry}
                disabled={loading}
              >
                {t.lesson.buildWarmUp}
              </Button>
            )}
          </div>
        </div>
      )}
      </PracticeSurface>

      {isSplit && revealed && lesson.lesson.reveal && (
        <div className="flex flex-col gap-3">
          <SectionLabel>{t.lesson.reveal}</SectionLabel>
          <p className="measure whitespace-pre-wrap text-body text-paper">
            {lesson.lesson.reveal}
          </p>

          {lesson.lesson.takeaway && (
            <Callout tone="signal" label={t.lesson.takeaway} className="mt-1">
              <p className="measure text-aside text-chalk">
                {lesson.lesson.takeaway}
              </p>
            </Callout>
          )}

          {lesson.lesson.ownership && (
            <Callout tone="neutral" label={t.lesson.ownership}>
              <p className="measure text-meta text-paper">
                {lesson.lesson.ownership}
              </p>
            </Callout>
          )}
        </div>
      )}



      <div className="border-t border-rule pt-4">
        {/* Kept where it is. `Finish session` in the header menu is the same
            action reached from the session level; this one is reached in context,
            at the end of a lesson, which is a different moment and a different
            question ("I have what I need from this") — so it is not a duplicate
            to be removed. Restructuring the lesson's own affordances is L-track
            work, not the header's. */}
        <button
          onClick={onFinish}
          className="font-mono text-micro text-graphite transition hover:text-chalk"
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
  // "Another pass" must list what is STILL unresolved — not everything the
  // learner ever stumbled on. `weak_spot` is sticky, so it kept offering a
  // second pass over units already mastered.
  const weak = graph.nodes.filter((n) => n.understanding === "unresolved");
  const understood = graph.nodes.filter((n) => n.understanding_state === "understood").length;

  return (
    <div className="flex h-full flex-col gap-5">
      <div className="flex shrink-0 gap-1 border-b border-rule">
        {(["summary", "map"] as const).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2 font-mono text-micro uppercase tracking-[0.12em] transition ${
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
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
              {t.completion.label}
            </span>
            <h2 className="font-display text-chapter font-medium tracking-tight text-chalk">
              {t.completion.heading(understood, graph.nodes.length)}
            </h2>
            <p className="measure text-body text-paper">
              {t.completion.body}
            </p>
          </div>

          {weak.length > 0 && (
            <div className="flex flex-col gap-3 rounded-card border border-rule bg-slab p-4">
              <span className="font-mono text-micro uppercase tracking-[0.14em] text-rust">
                {t.completion.anotherPass(weak.length)}
              </span>
              <ul className="flex flex-col gap-2.5">
                {weak.map((n) => (
                  <li key={n.id} className="flex flex-col gap-0.5">
                    <span className="text-aside font-medium text-chalk">{n.title}</span>
                    <span className="font-mono text-micro text-graphite">
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
            <Button variant="primary" size="md"
              onClick={onNewSession}
            >
              {t.completion.newSession}
            </Button>
            <Button variant="secondary" size="md"
              onClick={onFinish}
            >
              {t.completion.goHome}
            </Button>
          </div>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-hidden rounded-card border border-rule">
          <MapView
            nodes={graph.nodes}
            edges={graph.edges}
            currentNodeId={graph.current_node_id}
            progress={graph.progress}
            understanding={graph.understanding}
            areas={graph.areas}
            repoUrl={graph.repo_url}
            onNodeClick={() => {}}
            // The completion screen is a read-only recap; drilling into evidence
            // belongs to the live session, where the drawer has room.
            onOpenEvidence={() => {}}
          />
        </div>
      )}
    </div>
  );
}
