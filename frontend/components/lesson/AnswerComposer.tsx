"use client";

import { useState } from "react";

import Button from "@/components/ui/Button";
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
 * WHEN THE LESSON SHIPS `choices` the learner picks the INPUT, not the marking. A
 * selected option and a typed sentence leave through the same `onAnswerChange` /
 * `onSubmit` path and are graded against the objective identically — there is no
 * "correct" option here and none arrives from the server. The mode toggle clears
 * the answer on the way across so a stale selection is never posted as free text,
 * which keeps the one `answer` state with one writer. A text-only question (no
 * `choices`) renders exactly as it always did: one textarea, no radios, no toggle.
 *
 * Moved out unchanged, including `⌘↵` / `Ctrl↵` as a submit shortcut in the
 * textarea — the hint beside the button is the only place it is advertised, so it
 * is hidden in choose mode where it does not apply.
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
  /**
   * Four options, or empty for a text-only question — see `LessonBody.choices`.
   * Never a subset: the backend ships exactly four or none.
   */
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
   * the INTENT rather than the tool ("I'm stuck", not "Chat"), which is what
   * keeps it from reading as an unrestricted assistant parked beside a graded
   * question.
   *
   * Absent when the Tutor is not built into the bundle, so this file has no
   * opinion about the flag.
   */
  onStuck?: () => void;
}) {
  const hasChoices = choices.length > 0;
  // "choose" | "write". Offered only when there are options; a text-only question
  // is always "write" and shows no toggle.
  const [mode, setMode] = useState<"choose" | "write">(hasChoices ? "choose" : "write");
  const choosing = hasChoices && mode === "choose";

  const switchMode = () => {
    onAnswerChange("");
    setMode((m) => (m === "choose" ? "write" : "choose"));
  };

  return (
    <div data-tour="composer" className="flex flex-col gap-3">
      {/* The question is markdown too — Teaching writes `**Anchor 1:**` and
          backticked identifiers into it constantly, and the one string the
          learner has to parse to answer at all was the worst place to print
          syntax. */}
      <Prose text={prompt} size="lede" tone="chalk" />

      {choosing ? (
        // Native radios in a fieldset: arrow keys and the roving tab stop come
        // for free, and a screen reader announces "radio, 1 of 4". The real
        // input is visually hidden but fully operable; the row is the label.
        <fieldset disabled={loading} className="flex flex-col gap-1.5">
          {choices.map((option) => {
            const selected = answer === option;
            return (
              <label
                key={option}
                className={`flex min-h-[calc(44rem/16)] w-full cursor-pointer items-center gap-3 rounded-field border px-4 py-2.5 text-start text-aside transition ${
                  selected
                    ? "border-signal-dim bg-signal/15 text-signal"
                    : "border-rule text-chalk hover:border-signal-dim hover:text-signal"
                }`}
              >
                <input
                  type="radio"
                  name="lesson-answer-choice"
                  className="sr-only"
                  checked={selected}
                  onChange={() => onAnswerChange(option)}
                />
                <span
                  aria-hidden
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    selected ? "bg-signal" : "border border-rule"
                  }`}
                />
                {option}
              </label>
            );
          })}
        </fieldset>
      ) : (
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
      )}

      {hasChoices && (
        <button
          type="button"
          onClick={switchMode}
          disabled={loading}
          className="self-start font-mono text-micro text-graphite transition hover:text-signal"
        >
          {choosing ? t.lesson.writeOwnAnswer : t.lesson.chooseFromOptions}
        </button>
      )}

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
