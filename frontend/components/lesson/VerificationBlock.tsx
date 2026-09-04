"use client";

import Button from "@/components/ui/Button";
import ChoiceOrText from "@/components/lesson/ChoiceOrText";
import Prose from "@/components/ui/Prose";
import { t } from "@/lib/strings";

/**
 * A check on a named belief, or a fresh question about the objective — asked
 * instead of the lesson's own question.
 *
 * Two things here are load-bearing and were both bugs before they were rules.
 *
 * NO MODEL ANSWER AND NO REVEAL. The unit's explanation answers a different
 * question and is never shown here (§18.7). A re-assessment MAY still offer four
 * options (D10, revised): those are a fresh multiple choice for the NEW question,
 * graded against the objective like typed text, with no option flagged correct.
 * A verification question is always text-only — it passes `choices={[]}`.
 *
 * `Not now` CLEARS THE VERIFICATION, which is what brings the lesson's own
 * composer back — see the invariant in `AnswerComposer`. It is not a cancel that
 * leaves both on screen.
 *
 * The reply to this arrives with `classification: null` on purpose: a check is
 * evidence about beliefs, not a re-grade of the objective. That is why answering
 * it lands in the RESOLVED phase rather than FEEDBACK.
 */
export default function VerificationBlock({
  question,
  choices = [],
  answer,
  onAnswerChange,
  onSubmit,
  onDismiss,
  loading,
  error,
  onStuck,
}: {
  question: string;
  /** Four options for a re-assessment question, or `[]` (always `[]` for a check). */
  choices?: string[];
  answer: string;
  onAnswerChange: (value: string) => void;
  onSubmit: () => void;
  onDismiss: () => void;
  loading: boolean;
  /**
   * Why this exists: `AnswerComposer` has always rendered its failures and this
   * did not, so every way a check can fail — the 409s, a grading error — left the
   * learner pressing Submit against a button that did nothing and said nothing.
   */
  error?: string | null;
  /** Opens the Tutor in assessment mode. A link, never a second composer. */
  onStuck?: () => void;
}) {
  return (
    <div className="flex flex-col gap-3">
      <Prose text={question} size="lede" tone="chalk" />
      <p className="text-meta text-graphite">{t.lesson.verificationHelp}</p>

      <ChoiceOrText
        choices={choices}
        answer={answer}
        onAnswerChange={onAnswerChange}
        onSubmit={onSubmit}
        loading={loading}
      />

      {error && <p className="measure text-aside text-rust">{error}</p>}
      <div className="flex gap-2">
        <Button variant="primary" size="md" onClick={onSubmit} disabled={loading || !answer.trim()}>
          {loading ? t.lesson.grading : t.lesson.submit}
        </Button>
        <Button variant="secondary" size="md" onClick={onDismiss} disabled={loading}>
          {t.lesson.notNow}
        </Button>
        {onStuck && (
          <button
            type="button"
            onClick={onStuck}
            className="ms-auto font-mono text-micro text-graphite transition hover:text-signal"
          >
            {t.tutor.stuck}
          </button>
        )}
      </div>
    </div>
  );
}
