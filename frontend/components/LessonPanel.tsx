"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
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
  Anchor, Attempt, GraphNode, Lesson, NodeGap, RespondResult,
  SessionGraph, VerificationPrompt,
} from "@/lib/api";
import Callout from "@/components/ui/Callout";
import FeedbackCardNext from "@/components/lesson/FeedbackCardNext";
import CompletionScreen from "@/components/lesson/CompletionScreen";
import AnswerComposer from "@/components/lesson/AnswerComposer";
import AttemptHistory from "@/components/lesson/AttemptHistory";
import GapList from "@/components/lesson/GapList";
import LessonBrief from "@/components/lesson/LessonBrief";
import LessonCanvas from "@/components/lesson/LessonCanvas";
import LessonWorkspace from "@/components/lesson/LessonWorkspace";
import RevealBlock from "@/components/lesson/RevealBlock";
import SetupProse from "@/components/lesson/SetupProse";
import TracePath from "@/components/lesson/TracePath";
import VerificationBlock from "@/components/lesson/VerificationBlock";
import PracticeSurface from "@/components/ui/PracticeSurface";
import Button from "@/components/ui/Button";
import { isSplitSurfaces, lessonUi } from "@/lib/flags";
import { lessonPhase } from "@/lib/lessonPhase";
import { lessonBlocks } from "@/lib/lessonView";
import type { Surface } from "@/lib/lessonSurfaces";
import EarlierExplanations from "@/components/lesson/EarlierExplanations";
import { materialIsNew, supersededExplanations } from "@/lib/lessonHistory";
import { FAILED } from "@/lib/verdict";
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
  /**
   * Which surface to render, under `surfaces` only.
   *
   * Owned by the session page because the TAB is owned there — R5 keeps tab
   * selection out of anything that can see a phase, and this component is full of
   * phase. It receives the consequence of a navigation decision, never makes one.
   */
  surface?: Surface | null;
  /**
   * Something landed in a surface. The page decides whether that is news — it owns
   * the tab, and a change in the surface the learner is looking at is not news.
   *
   * R1's mitigation, and the reason the panel reports rather than decides: a change
   * announced only inside the surface that changed is announced to nobody, and this
   * component cannot see which surface is on screen.
   */
  onSurfaceChanged?: (surface: Surface) => void;
  /** Take the learner to a surface. Always from an explicit control of theirs. */
  onGoToSurface?: (surface: Surface) => void;
}

export default function LessonPanel({
  sessionId, nodeId, node, position, total, isPrerequisite,
  graph, onFileClick, onAdvance, onRespond, finished, onFinish, onLeave, surface,
  onSurfaceChanged, onGoToSurface,
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
  // The Mutator refused a warm-up for THIS node. Kept out of `result` on purpose:
  // it outlives any one answer, because what it records is a fact about the
  // stop's surroundings rather than about the attempt that asked.
  const [warmUpDeclined, setWarmUpDeclined] = useState(false);

  useEffect(() => {
    setLesson(null);
    setError(null);
    setLoading(true);
    getLesson(sessionId)
      .then(setLesson)
      .catch((e) => setError(errorText(e.message)))
      .finally(() => setLoading(false));
  }, [sessionId, nodeId]);

  // Moving to a different node is what clears the answer in progress — and the
  // refusal with it, since a different stop has a different foundation.
  useEffect(() => {
    setResult(null);
    setAnswer("");
    setChecked(null);
    setWarmUpDeclined(false);
    // AND THE OUTSTANDING CHECK. A verification question belongs to the gap it
    // was written for, on the node that carries it. Leaving it set turned the
    // NEXT stop into `VERIFY` — `lessonPhase` reads `verification` — so its
    // Submit posted `kind: "verification"` for a node with nothing pending, the
    // backend answered 409 `no_pending_verification`, and the learner pressed a
    // button that did nothing at all. Hit while re-validating the other fixes.
    //
    // Clearing is the honest minimum, not the whole answer: the server still
    // holds `pending_verification`, and carrying it back when the learner returns
    // needs it on the wire (F101). Dropping it here loses nothing they can see.
    setVerification(null);
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
      // A verdict, a rationale, and possibly a new gap: all of it lands in
      // Understanding. Reported even when the learner is looking at it — the page
      // is what knows whether that makes it news.
      onSurfaceChanged?.("understanding");
      // The explanation unlocks on the first graded answer, which is material
      // appearing in Lesson while the learner is somewhere else.
      if (!revealed && lesson?.lesson.reveal) onSurfaceChanged?.("lesson");
      // A re-teach replaced the cached lesson with one that names the
      // misconception. Pull it, so what is on screen is the corrected lesson
      // rather than the one that misled them.
      if (res.adaptation?.retaught) {
        getLesson(sessionId).then(setLesson).catch(() => {});
        // The prose itself changed. This is the case R1 was written for: it happens
        // in Lesson, it happens because of something done in Understanding, and
        // nothing about the verdict card would tell the learner unless we say so.
        onSurfaceChanged?.("lesson");
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
        // RECORD THE REFUSAL. The card used to infer "declined" from the
        // GRADING response — `adaptation.kind === "prerequisite"` with no
        // matching mutation — which cannot see a decline that happens here, on
        // the retry call. So the Mutator answered `no_useful_prerequisite`, the
        // sentence below was shown, and "Build me a warm-up" stayed on offer.
        //
        // Node-scoped, and kept for the node's lifetime: both refusals
        // (`no_useful_prerequisite` — nothing smaller is a foundation — and
        // `prerequisite_exists`) are facts about this stop's surroundings, not
        // about the answer that preceded the request. Answering again does not
        // make a foundation appear.
        setWarmUpDeclined(true);
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
      onSurfaceChanged?.("understanding");
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
      onSurfaceChanged?.("understanding");
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
    // Refused once for this stop. "Never offer what would be declined" is the
    // whole point of these gates, and a decline recorded on the retry call was
    // invisible to every one of them.
    !warmUpDeclined &&
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

  /**
   * Which blocks the canvas shows, and at what weight — see `lib/lessonView.ts`,
   * where §3a is answered. Computed on both paths so the numbers are measurable
   * either way; only the `next` path renders from it.
   */
  const ui = lessonUi();
  // Under `surfaces` the page tells us which surface to draw; under `next` there is
  // one column and `undefined` is what tells `LessonCanvas` to draw all of it.
  const drawing: Surface | undefined = isSplitSurfaces(ui)
    ? surface ?? "lesson"
    : undefined;
  // R3's third mitigation, read from the attempt history so it survives a reload.
  // Only offered on the split: the group is Lesson's, and `next` has no Lesson to
  // be a document of.
  const superseded = drawing ? supersededExplanations(attempts) : [];
  // Did the last answer rewrite what is on this surface? The consequence line says
  // so on the Understanding side at the moment it happens; this is what makes the
  // claim good for a learner who arrives at Lesson later, or after a reload.
  const rewritten = drawing === "lesson" && materialIsNew(attempts);
  const blocks = lessonBlocks({
    phase,
    multiAnchor: anchors.length > 1,
    openGapCount: openGaps.length,
    attemptCount: attempts.length,
    revealed,
    hasReveal: isSplit && Boolean(lesson.lesson.reveal),
    // Zero on the single canvas, which is how `next` stays exactly as it was: the
    // block is `absent` and nothing renders.
    supersededCount: superseded.length,
  });

  // The two handlers that used to be inline in the feedback branch, named so the
  // card can take callbacks instead of state setters. Same bodies, same effects.
  const answerAgain = () => {
    setResult(null);
    setAnswer("");
  };
  /**
   * Take the learner to a block the brief only counted.
   *
   * Rect arithmetic rather than `scrollIntoView`, for two measured reasons. It did
   * not move at all with `behavior: "smooth"` — that needs an animation frame loop
   * — and even `block: "center"` cannot know about the PINNED BRIEF, so any
   * alignment that puts the target near the top of the scrollport puts it
   * underneath the header instead. The offset here subtracts the brief's real
   * height, read at call time so the text-size dial cannot stale it.
   *
   * Same lesson as the source pane, arrived at from the other direction: there it
   * was `offsetTop` measuring against the wrong ancestor, here it is a scroll API
   * that has no idea part of the scrollport is covered.
   */
  /**
   * Take the learner to a block the brief's counters name.
   *
   * L5, adapted to the split. The counters live in the brief, the brief renders on
   * BOTH surfaces, and the blocks they point at — the gap list, the attempt history
   * — belong to Understanding. So on the Lesson tab `document.getElementById` found
   * nothing and this returned silently: a button that looked live, said
   * "3 unresolved", and did nothing at all.
   *
   * Now it crosses first. Switching surface is a learner action — they clicked a
   * counter — so it goes through the same tab reducer as everything else and R5 is
   * untouched. The scroll then happens on the next frame, because the surface it is
   * scrolling within has not rendered yet at the moment of the click.
   */
  const revealBlock = (id: string) => {
    if (!document.getElementById(id) && drawing === "lesson" && onGoToSurface) {
      onGoToSurface("understanding");
      // One frame, not a timeout: the block exists as soon as the other surface
      // commits, and waiting longer than that would let the eye arrive first.
      requestAnimationFrame(() => requestAnimationFrame(() => revealBlock(id)));
      return;
    }
    const target = document.getElementById(id);
    if (!target) return;
    let box: HTMLElement | null = target.parentElement;
    while (box && box.scrollHeight <= box.clientHeight) box = box.parentElement;
    if (!box) return;
    const brief = box.querySelector("[data-lesson-brief]");
    const clearance = (brief?.getBoundingClientRect().height ?? 0) + 12;
    const top =
      box.scrollTop + target.getBoundingClientRect().top - box.getBoundingClientRect().top - clearance;
    // The same short-hop-only rule the source pane uses: animate a jump the eye
    // can follow, and cut straight to a long one rather than making the learner
    // watch the whole column go past.
    const goal = Math.max(0, top);
    const near = Math.abs(goal - box.scrollTop) < box.clientHeight * 1.5;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    box.scrollTo({ top: goal, behavior: near && !still ? "smooth" : "auto" });
  };

  const startWarmUp = async () => {
    setLoading(true);
    try {
      await onAdvance();
    } finally {
      setLoading(false);
    }
  };

  return (
    // The one thing L1 renders: an invisible attribute, so a test can assert that
    // the derived phase agrees with the blocks actually on screen rather than
    // re-testing the pure function against itself. Zero visual diff, and it stays
    // useful as the hook L3 and L4's tests key off.
    <div data-lesson-phase={phase}>
      <LessonWorkspace
        /* The tab switch resets the shared scroller, so re-measure on the same
           signal rather than waiting for the programmatic scroll's event. */
        remeasureOn={drawing}
        brief={(collapsed) => (
          <LessonBrief
            node={node}
            position={position}
            total={total}
            isPrerequisite={isPrerequisite}
            onFileClick={onFileClick}
            openGapCount={openGaps.length}
            attemptCount={attempts.length}
            onShowGaps={() => revealBlock("lesson-gaps")}
            onShowAttempts={() => revealBlock("lesson-attempts")}
            collapsed={collapsed}
          />
        )}
      >

      {/* ONE canvas model now (L5). The pre-redesign renderer used to sit in an
          else branch here — the stack exactly as it shipped, kept reachable so the
          new information architecture could be proven before it was the only path.
          It has been proven twice over: by L4's measurements against it, and by
          S6's against L4. Keeping a third arrangement alive meant every behaviour
          change had to be made twice or consciously not made twice, which is how
          `warmUpDeclined` came to be inferred two different ways.

          `next` and `surfaces` both render from here and differ only in PLACEMENT —
          `surfaces` draws one surface at a time, `next` draws the column. Same
          blocks, same view model, same phase. `next` stays because it is the
          baseline S6 measured against and the thing a human has not yet chosen
          between. */}
          {/* "You came back and got it" is evidence about the LEARNER, so it
              belongs with the rest of that on Understanding. On the single canvas
              there was nowhere else for it to be. */}
          {/* S5's `new` marking. On Lesson, above the material, because that is
              what it is about — and only there: on Understanding the consequence
              line already said it, in the card that caused it. */}
          {rewritten && (
            <Callout tone="signal" label={t.lesson.newMaterialLabel}>
              <p className="text-meta text-chalk">{t.lesson.newMaterialBody}</p>
            </Callout>
          )}

          {recovered && drawing !== "lesson" && (
            <Callout tone="jade" label={t.lesson.recoveredLabel}>
              <p className="text-meta text-paper">
                {t.lesson.recoveredBody}{" "}
                <span className="text-chalk">“{warmUpTitle}”</span>
                {t.lesson.recoveredBodyEnd}
              </p>
            </Callout>
          )}

          <LessonCanvas
            blocks={blocks}
            surface={drawing}
            labels={{
              setup: isSplit ? t.lesson.setup : t.lesson.walkthrough,
              setupMirror: t.lesson.setupMirror,
              tracePath: t.lesson.tracePath,
              tracePathCount: anchors.length,
              gaps: t.lesson.gapsHeading,
              gapsCount: openGaps.length,
              attempts: t.lesson.yourAnswers(attempts.length),
              earlier: t.lesson.earlierExplanations(superseded.length),
              question: t.lesson.questionAsked,
            }}
            earlier={<EarlierExplanations versions={superseded} />}
            /* Text only. The composer lives in `question` and renders only while
               that block is open, which is what keeps "exactly one composer" true
               while the question stays re-readable. */
            questionEcho={
              <p className="measure whitespace-pre-wrap text-aside text-paper">
                {lesson.lesson.prompt}
              </p>
            }
            setup={
              <div className="flex flex-col gap-3">
                {isSplit && lesson.lesson.why_now && (
                  <p className="measure border-s-2 border-rule ps-3 text-meta italic text-graphite">
                    {lesson.lesson.why_now}
                  </p>
                )}
                <SetupProse
                  isSplit={isSplit}
                  body={isSplit ? lesson.lesson.setup : lesson.lesson.walkthrough}
                />
              </div>
            }
            tracePath={<TracePath anchors={anchors} onFileClick={onFileClick} />}
            gaps={
              <div id="lesson-gaps">
                <GapList gaps={openGaps} onWaive={onWaive} disabled={loading} />
              </div>
            }
            attempts={
              <div id="lesson-attempts">
                <AttemptHistory attempts={attempts} />
              </div>
            }
            question={
              <PracticeSurface label={practiceLabel}>
                {verification ? (
                  <VerificationBlock
                    question={verification.question}
                    answer={answer}
                    onAnswerChange={setAnswer}
                    onSubmit={onSubmitVerification}
                    onDismiss={() => setVerification(null)}
                    loading={loading}
                    error={error}
                  />
                ) : (
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
              </PracticeSurface>
            }
            feedback={
              result && (
                <PracticeSurface label={practiceLabel}>
                  <FeedbackCardNext
                    result={result}
                    isCheck={isCheck}
                    checkOutcome={checkOutcome}
                    closed={closed}
                    checkedAnswer={checked?.answer}
                    openGaps={openGaps}
                    warmUpInserted={warmUpInserted}
                    // ONE gate for the whole table. The assessment path uses the
                    // panel's own flag; on a check that flag is false by
                    // construction while a warm-up is still deliberately reachable
                    // while something is unresolved, so the union is what
                    // `feedbackActions` needs to obey "never offer what would be
                    // declined" without knowing which path it is on.
                    warmUpAvailable={
                      (canRequestWarmUp || (isCheck && !warmUpInserted)) && !warmUpDeclined
                    }
                    warmUpDeclined={warmUpDeclined}
                    canAnswerAgain={canAnswerAgain}
                    // Verification is available whenever something is open to
                    // verify. Exhaustion and the node's remediation cap are not on
                    // the node wire, so a refusal is reported (`nothing_to_verify`)
                    // rather than pre-empted.
                    checkAvailable={openGaps.length > 0}
                    loading={loading}
                    verifying={verifying}
                    error={error}
                    verdictRef={verdictRef}
                    onAdvanceStop={handleAdvance}
                    onCheckUnderstanding={onCheckUnderstanding}
                    onBuildWarmUp={handleRetry}
                    onAnswerAgain={answerAgain}
                    onStartWarmUp={startWarmUp}
                    // The consequence line's control, under `surfaces` only: the
                    // line says the stop was rewritten, and on the split the
                    // rewritten thing is one tab away. Passing a callback rather
                    // than a tab name keeps navigation the page's business (R5).
                    onReadInLesson={
                      drawing && onGoToSurface ? () => onGoToSurface("lesson") : undefined
                    }
                  />
                </PracticeSurface>
              )
            }
            reveal={
              lesson.lesson.reveal ? (
                <RevealBlock
                  reveal={lesson.lesson.reveal}
                  takeaway={lesson.lesson.takeaway}
                  ownership={lesson.lesson.ownership}
                />
              ) : null
            }
          />

          <div className="border-t border-rule pt-4">
            <button
              onClick={onFinish}
              className="font-mono text-micro text-graphite transition hover:text-chalk"
            >
              {t.lesson.finishEarly}
            </button>
          </div>
      </LessonWorkspace>
    </div>
  );
}
