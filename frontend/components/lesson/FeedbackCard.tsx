"use client";

import type { RefObject } from "react";
import type { NodeGap, RespondResult } from "@/lib/api";
import Button from "@/components/ui/Button";
import Callout from "@/components/ui/Callout";
import { FAILED, NEUTRAL, VERDICT_COLOR } from "@/lib/verdict";
import { t } from "@/lib/strings";

/**
 * What happened to the answer that was just given.
 *
 * THIS IS THE BLOCK §3a IS ABOUT. Sixteen independent conditional sub-blocks,
 * eleven `<Button>` call sites of which one to four render at once, twenty-one
 * copy strings — and it is moved here VERBATIM, because L2's job is to relocate
 * code, not to decide what should survive. The nineteen props it takes are not a
 * design; they are the measurement. A presentational block needing nineteen
 * inputs is the same finding as sixteen conditionals, stated in a second way.
 *
 * L4 is where this gets restructured, against §3a's five questions:
 *   1. after a CORRECT answer, what should be here beyond the verdict and Next?
 *   2. do the adaptation notices (retaught, pruned, warm-up status) belong to the
 *      feedback at all, or to the adaptation channel in A1?
 *   3. should gaps collapse to the brief's counter the moment a verdict lands?
 *   4. are `takeaway` and `ownership` a third thing competing with verdict and
 *      reveal? (they are in `RevealBlock`, not here)
 *   5. is the attempt history ever wanted DURING feedback?
 *
 * Two things inside must not be lost while that happens, both of them scars:
 *
 * A CHECK IS NOT A RE-GRADE. Every branch keyed off `classification` is silent on
 * the check path because the backend returns null there deliberately, which is
 * why `isCheck` gets its own actions — without them the only reachable button
 * after a correct check was "Build me a warm-up", offered because
 * `null !== "understood"` happened to be true.
 *
 * "TRY AGAIN" IS NOT OFFERED WHILE A GAP IS OPEN. It cleared the form and
 * re-asked the very question whose answer `reveal` had just given away, so
 * passing proved only that the learner had read the page. With a gap open the
 * primary asks a NEW question about the same misconception instead (§18.7).
 */
export default function FeedbackCard({
  result,
  isCheck,
  checkOutcome,
  closed,
  checkedAnswer,
  adaptation,
  openGaps,
  warmUpInserted,
  canRequestWarmUp,
  canAnswerAgain,
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
  adaptation: RespondResult["adaptation"];
  openGaps: NodeGap[];
  warmUpInserted: boolean;
  canRequestWarmUp: boolean;
  canAnswerAgain: boolean;
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
  return (
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
      {isCheck && checkedAnswer && (
        <div className="flex flex-col gap-1">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
            {t.lesson.youWrote}
          </span>
          <p className="measure whitespace-pre-wrap text-meta text-paper">
            {checkedAnswer}
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
                onClick={onAdvanceStop}
                disabled={loading}
              >
                {loading ? t.lesson.loadingShort : t.lesson.nextStop}
              </Button>
            )}
            {openGaps.length > 0 && (
              <Button variant="secondary" size="md"
                onClick={onAdvanceStop}
                disabled={loading}
              >
                {loading ? t.lesson.loadingShort : t.lesson.nextStop}
              </Button>
            )}
            {/* Still reachable when something is unresolved, but never the
                whole response to a correct answer. */}
            {openGaps.length > 0 && !warmUpInserted && (
              <Button variant="ghost"
                onClick={onBuildWarmUp}
                disabled={loading}
              >
                {t.lesson.buildWarmUp}
              </Button>
            )}
          </>
        )}

        {result.classification === "understood" && (
          <Button variant="primary" size="md"
            onClick={onAdvanceStop}
            disabled={loading}
          >
            {loading ? t.lesson.loadingShort : t.lesson.nextStop}
          </Button>
        )}

        {/* Partly there: moving on is the default. The warm-up offer is
            shared with every other non-understood state, below. */}
        {result.classification === "partial" && (
          <Button variant="primary" size="md"
            onClick={onAdvanceStop}
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
            onClick={onAnswerAgain}
            disabled={loading}
          >
            {t.lesson.tryAgain}
          </Button>
        )}

        {FAILED.includes(result.classification) && (
          <>
            {result.mutation?.kind === "prerequisite" && (
              <Button variant="primary" size="md"
                onClick={onStartWarmUp}
                disabled={loading}
              >
                {loading ? t.lesson.loadingShort : t.lesson.startWarmUp}
              </Button>
            )}
            <Button variant="secondary" size="md"
              onClick={onAdvanceStop}
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
            onClick={onBuildWarmUp}
            disabled={loading}
          >
            {t.lesson.buildWarmUp}
          </Button>
        )}
      </div>
    </div>
  );
}
