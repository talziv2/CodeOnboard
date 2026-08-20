"use client";

import Button from "@/components/ui/Button";
import { t } from "@/lib/strings";

/**
 * The lesson's own question, and the one place an answer is written.
 *
 * THE SINGLE-COMPOSER INVARIANT LIVES HERE. This and `VerificationBlock` bind the
 * same `answer` state in the panel, so rendering both at once put two textareas on
 * screen that mirrored each other's text, beneath two buttons both labelled
 * "Submit" that did different things. That was D2. The panel decides which of the
 * two is on screen; neither component may be made to render alongside the other.
 *
 * Moved out unchanged, including `⌘↵` / `Ctrl↵` as a submit shortcut — the hint
 * beside the button is the only place it is advertised, so removing one without
 * the other would strand it.
 */
export default function AnswerComposer({
  prompt,
  answer,
  onAnswerChange,
  onSubmit,
  onSkip,
  loading,
  error,
}: {
  prompt: string;
  answer: string;
  onAnswerChange: (value: string) => void;
  onSubmit: () => void;
  onSkip: () => void;
  loading: boolean;
  error: string | null;
}) {
  return (
    <div className="flex flex-col gap-3">
      <p className="measure text-lede text-chalk">{prompt}</p>
      <textarea
        rows={4}
        className="w-full resize-none rounded-field border border-rule bg-trench p-3 text-start text-aside text-chalk placeholder:text-graphite focus:border-signal-dim"
        placeholder={t.lesson.answerPlaceholder}
        value={answer}
        onChange={(e) => onAnswerChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            onSubmit();
          }
        }}
        disabled={loading}
      />
      {error && <p className="text-aside text-rust">{error}</p>}
      <div className="flex items-center gap-3">
        <Button variant="primary" size="md" onClick={onSubmit} disabled={loading || !answer.trim()}>
          {loading ? t.lesson.grading : t.lesson.submit}
        </Button>
        <Button variant="secondary" size="md" onClick={onSkip} disabled={loading}>
          {t.lesson.skipStop}
        </Button>
        <span className="ms-auto font-mono text-micro text-graphite">
          {t.lesson.submitHint}
        </span>
      </div>
    </div>
  );
}
