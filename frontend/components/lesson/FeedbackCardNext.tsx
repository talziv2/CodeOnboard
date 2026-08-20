"use client";

import type { RefObject } from "react";
import type { NodeGap, RespondResult } from "@/lib/api";
import Button from "@/components/ui/Button";
import Callout from "@/components/ui/Callout";
import { feedbackActions, plannedActions, type ActionId } from "@/lib/feedbackActions";
import { consequenceLine, keyPoint } from "@/lib/feedbackSummary";
import { NEUTRAL, VERDICT_COLOR } from "@/lib/verdict";
import { t } from "@/lib/strings";

/**
 * What happened to the answer, said once each.
 *
 * The legacy card is sixteen independent conditional sub-blocks with up to four
 * equally weighted buttons. This is the same information at the same fidelity, in a
 * fixed order, with every decision made by a tested pure function rather than by a
 * nested conditional:
 *
 *   key point         `feedbackSummary.keyPoint` — the ladder in §2
 *   rationale         the Grader's own words, NEVER collapsed while a verdict is up
 *   help              the hint or follow-up, when the system offered one
 *   consequence       `feedbackSummary.consequenceLine` — ONE line, not five
 *   what closed       on a check only: the gaps this answer shut, by name
 *   your words        on a check only: otherwise the answer is nowhere
 *   actions           `feedbackActions` — exactly one primary
 *
 * WHY THE KEY POINT DOES NOT REPLACE THE RATIONALE. The rationale sits immediately
 * below it and is never collapsed, because a condensation the learner can act on
 * without reading is an invitation to skip. The key point orients; it is not a
 * summary to be satisfied by.
 *
 * THE ACTIONS ARE INSIDE THIS CARD, and the card sits above the explanation — see
 * `LessonCanvas`. That is what stops the primary being stranded below a long read,
 * and it is why the explanation can be as long as it needs to be.
 *
 * Two scars carried across deliberately. A CHECK IS NOT A RE-GRADE: its
 * `classification` is null by design, so the action plan takes `isCheck` and never
 * infers from the classification — which is how "Build me a warm-up" once became the
 * only button after a correct check. And "TRY AGAIN" IS NOT OFFERED WHILE A GAP IS
 * OPEN: `feedbackActions` returns `check` there instead, because re-asking the
 * question whose answer the reveal just gave away proves only that the page was
 * read (§18.7).
 */
export default function FeedbackCardNext({
  result,
  isCheck,
  checkOutcome,
  closed,
  checkedAnswer,
  openGaps,
  warmUpInserted,
  warmUpAvailable,
  warmUpDeclined,
  canAnswerAgain,
  checkAvailable,
  loading,
  verifying,
  error,
  verdictRef,
  onAdvanceStop,
  onCheckUnderstanding,
  onBuildWarmUp,
  onAnswerAgain,
  onStartWarmUp,
}: {
  result: RespondResult;
  isCheck: boolean;
  checkOutcome: { label: string; color: string };
  closed: NodeGap[];
  checkedAnswer: string | undefined;
  openGaps: NodeGap[];
  warmUpInserted: boolean;
  warmUpAvailable: boolean;
  /** The Mutator refused one for this node — on EITHER call. Panel-owned. */
  warmUpDeclined: boolean;
  canAnswerAgain: boolean;
  checkAvailable: boolean;
  loading: boolean;
  verifying: boolean;
  error: string | null;
  verdictRef: RefObject<HTMLDivElement | null>;
  onAdvanceStop: () => void;
  onCheckUnderstanding: () => void;
  onBuildWarmUp: () => void;
  onAnswerAgain: () => void;
  onStartWarmUp: () => void;
}) {
  const verdictWord = isCheck
    ? checkOutcome.label
    : t.lesson.verdict[result.classification] ?? result.classification;
  const verdictColor = isCheck
    ? checkOutcome.color
    : VERDICT_COLOR[result.classification] ?? NEUTRAL;

  // On a check the key point IS the outcome word — a check reports what closed
  // rather than diagnosing a new misconception, and composing "you're working from"
  // out of a gap that just closed would be backwards.
  const headline = isCheck ? verdictWord : keyPoint(result, openGaps, verdictWord);
  const consequence = consequenceLine(result);
  const help = result.adaptation?.text;

  const plan = feedbackActions({
    classification: result.classification,
    isCheck,
    openGapCount: openGaps.length,
    warmUpInserted,
    // Declined, by EITHER route. The automatic one is still read from the grading
    // response: the backend chose `prerequisite` and produced no mutation. The
    // other — the learner pressed the button and the Mutator refused — happens on
    // a call this response knows nothing about, so the panel records it and passes
    // it in. Inferring both from `result` is why a refused warm-up stayed on offer.
    warmUpDeclined:
      warmUpDeclined ||
      (result.adaptation?.kind === "prerequisite" &&
        result.mutation?.kind !== "prerequisite"),
    warmUpAvailable,
    canAnswerAgain,
    checkAvailable,
  });

  const label: Record<ActionId, string> = {
    next: loading ? t.lesson.loadingShort : t.lesson.nextStop,
    check: verifying
      ? t.lesson.verifyCtaBusy
      : isCheck
        ? t.lesson.checkAnother
        : t.lesson.verifyCta,
    warmUp: t.lesson.buildWarmUp,
    answerAgain: t.lesson.tryAgain,
    startWarmUp: loading ? t.lesson.loadingShort : t.lesson.startWarmUp,
    skipWarmUp: t.lesson.skipItMoveOn,
    moveOn: loading ? t.lesson.loadingShort : t.lesson.moveOnAnyway,
  };
  const onClick: Record<ActionId, () => void> = {
    next: onAdvanceStop,
    check: onCheckUnderstanding,
    warmUp: onBuildWarmUp,
    answerAgain: onAnswerAgain,
    startWarmUp: onStartWarmUp,
    skipWarmUp: onAdvanceStop,
    moveOn: onAdvanceStop,
  };
  const busy = (id: ActionId) => (id === "check" ? loading || verifying : loading);
  const actions = plannedActions(plan);

  return (
    <div
      ref={verdictRef}
      // Focused after grading so the verdict is what a keyboard or screen reader
      // lands on, not just what the viewport moved to.
      tabIndex={-1}
      className="flex flex-col gap-3"
    >
      <p
        className="measure text-lede"
        style={{ color: verdictColor }}
      >
        {headline}
      </p>

      {/* Never collapsed. The key point above orients; this is the reasoning, and
          hiding it is what would turn a condensation into a substitute. */}
      <p className="measure text-aside text-paper">{result.rationale}</p>

      {help && (
        <Callout
          tone="signal"
          label={result.adaptation?.kind === "hint" ? t.lesson.hint : t.lesson.followup}
        >
          <p className="measure text-aside text-chalk">{help}</p>
        </Callout>
      )}

      {consequence && (
        <p className="measure border-s-2 border-rule ps-3 text-meta text-graphite">
          {consequence}
        </p>
      )}

      {/* A closed gap is the half that is otherwise unrecoverable: by the time this
          renders it has already left the gap list above. What is still open is
          deliberately NOT re-listed — the brief's counter and the collapsed list
          are the authoritative copy of that. */}
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

      {isCheck && closed.length === 0 && (
        <p className="measure text-meta text-graphite">{t.lesson.checkNothingClosed}</p>
      )}

      {/* A verification answer is kept out of "Your answers" — it carries no
          classification, so including it would blank a row and corrupt `latest` —
          which left the learner's own words nowhere at all once the composer
          cleared. */}
      {isCheck && checkedAnswer && (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
            {t.lesson.youWrote}
          </span>
          <p className="measure whitespace-pre-wrap text-meta text-paper">{checkedAnswer}</p>
        </div>
      )}

      {error && <p className="text-aside text-rust">{error}</p>}

      <div className="flex flex-wrap items-center gap-3">
        {actions.map((id, i) => (
          <Button
            key={id}
            // Exactly one primary, by construction: the plan's first action is the
            // primary and there is only ever one plan.
            variant={i === 0 ? "primary" : i === 1 ? "secondary" : "ghost"}
            size={i === 2 ? undefined : "md"}
            onClick={onClick[id]}
            disabled={busy(id)}
          >
            {label[id]}
          </Button>
        ))}
      </div>
    </div>
  );
}
