"use client";

import Button from "@/components/ui/Button";
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
}: {
  question: string;
  answer: string;
  onAnswerChange: (value: string) => void;
  onSubmit: () => void;
  onDismiss: () => void;
  loading: boolean;
}) {
  return (
    <div className="flex flex-col gap-3">
      <p className="measure text-lede text-chalk">{question}</p>
      <p className="text-meta text-graphite">{t.lesson.verificationHelp}</p>
      <textarea
        value={answer}
        onChange={(e) => onAnswerChange(e.target.value)}
        placeholder={t.lesson.answerPlaceholder}
        rows={4}
        className="w-full resize-none rounded-field border border-rule bg-trench p-3 text-start text-aside text-chalk placeholder:text-graphite focus:border-signal-dim"
      />
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
