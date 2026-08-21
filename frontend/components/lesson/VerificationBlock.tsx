"use client";

import Button from "@/components/ui/Button";
import Prose from "@/components/ui/Prose";
import { t } from "@/lib/strings";

/**
 * A check on a named belief, asked instead of the lesson's own question.
 *
 * Two things here are load-bearing and were both bugs before they were rules.
 *
 * NO MODEL ANSWER AND NO REVEAL. Nothing is sent and nothing is rendered, because
 * showing the answer beside the question is what made re-asking meaningless
 * (§18.7).
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
  answer,
  onAnswerChange,
  onSubmit,
  onDismiss,
  loading,
  error,
}: {
  question: string;
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
}) {
  return (
    <div className="flex flex-col gap-3">
      <Prose text={question} size="lede" tone="chalk" />
      <p className="text-meta text-graphite">{t.lesson.verificationHelp}</p>
      <textarea
        value={answer}
        onChange={(e) => onAnswerChange(e.target.value)}
        placeholder={t.lesson.answerPlaceholder}
        rows={4}
        className="w-full resize-none rounded-field border border-rule bg-trench p-3 text-start text-aside text-chalk placeholder:text-graphite focus:border-signal-dim"
      />
      {error && <p className="measure text-aside text-rust">{error}</p>}
      <div className="flex gap-2">
        <Button variant="primary" size="md" onClick={onSubmit} disabled={loading || !answer.trim()}>
          {loading ? t.lesson.grading : t.lesson.submit}
        </Button>
        <Button variant="secondary" size="md" onClick={onDismiss} disabled={loading}>
          {t.lesson.notNow}
        </Button>
      </div>
    </div>
  );
}
