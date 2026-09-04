"use client";

import { useState } from "react";

import Button from "@/components/ui/Button";
import ChoiceOrText from "@/components/lesson/ChoiceOrText";
import Prose from "@/components/ui/Prose";
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
 * WHEN THE LESSON SHIPS `choices` the learner picks the INPUT, not the marking —
 * `ChoiceOrText` holds that logic, shared with `VerificationBlock`. A selected
 * option and a typed sentence leave through the same `onAnswerChange` / `onSubmit`
 * and are graded against the objective identically; there is no "correct" option.
 * A text-only question (no `choices`) renders exactly as it always did.
 */
export default function AnswerComposer({
  prompt,
  choices = [],
  answer,
  onAnswerChange,
  onSubmit,
  onSkip,
  loading,
  error,
  onStuck,
}: {
  prompt: string;
  /** Four options, or empty for a text-only question — see `LessonBody.choices`. */
  choices?: string[];
  answer: string;
  onAnswerChange: (value: string) => void;
  onSubmit: () => void;
  onSkip: () => void;
  loading: boolean;
  error: string | null;
  /**
   * Opens the Tutor, already in assessment mode.
   *
   * A LINK, never a second textarea — the single-composer invariant this file
   * documents is exactly what a second input here would break. The label names
   * the INTENT rather than the tool ("I'm stuck", not "Chat").
   *
   * Absent when the Tutor is not built into the bundle, so this file has no
   * opinion about the flag.
   */
  onStuck?: () => void;
}) {
  const [choosing, setChoosing] = useState(choices.length > 0);

  return (
    <div data-tour="composer" className="flex flex-col gap-3">
      {/* The question is markdown too — Teaching writes `**Anchor 1:**` and
          backticked identifiers into it constantly, and the one string the
          learner has to parse to answer at all was the worst place to print
          syntax. */}
      <Prose text={prompt} size="lede" tone="chalk" />

      {/* Says the missing multiple choice is a property of THIS question, not a
          page that failed to load one. Absent once options are present. */}
      {choices.length === 0 && (
        <p className="font-mono text-micro text-graphite">{t.lesson.textOnlyQuestion}</p>
      )}

      <ChoiceOrText
        choices={choices}
        answer={answer}
        onAnswerChange={onAnswerChange}
        onSubmit={onSubmit}
        loading={loading}
        onChoosingChange={setChoosing}
      />

      {error && <p className="text-aside text-rust">{error}</p>}
      <div className="flex items-center gap-3">
        <Button variant="primary" size="md" onClick={onSubmit} disabled={loading || !answer.trim()}>
          {loading ? t.lesson.grading : t.lesson.submit}
        </Button>
        <Button variant="secondary" size="md" onClick={onSkip} disabled={loading}>
          {t.lesson.skipStop}
        </Button>
        {onStuck && (
          <button
            type="button"
            onClick={onStuck}
            className="font-mono text-micro text-graphite transition hover:text-signal"
          >
            {t.tutor.stuck}
          </button>
        )}
        {!choosing && (
          <span className="ms-auto font-mono text-micro text-graphite">
            {t.lesson.submitHint}
          </span>
        )}
      </div>
    </div>
  );
}
