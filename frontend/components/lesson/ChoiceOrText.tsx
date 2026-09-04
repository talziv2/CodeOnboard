"use client";

import { useEffect, useState } from "react";

import { t } from "@/lib/strings";

/**
 * One answer input, two ways to give it: pick from four options, or type.
 *
 * THE INPUT, NOT THE MARKING. A selected option and a typed sentence both leave
 * through the one `onAnswerChange` and are graded the same way — against the
 * objective. There is no "correct" option here and none arrives from the server.
 * The mode toggle clears the answer on the way across so a stale selection is
 * never posted as free text, and vice versa: the single `answer` state keeps one
 * writer. With no `choices` this is exactly a textarea — no radios, no toggle.
 *
 * Shared by `AnswerComposer` (the unit's first prompt) and `VerificationBlock`
 * (a re-assessment question), so the four-option input looks and behaves the
 * same wherever a question offers it.
 */
export default function ChoiceOrText({
  choices,
  answer,
  onAnswerChange,
  onSubmit,
  loading,
  placeholder = t.lesson.answerPlaceholder,
  onChoosingChange,
}: {
  choices: string[];
  answer: string;
  onAnswerChange: (value: string) => void;
  /** Fired on ⌘↵ / Ctrl↵ in the textarea. */
  onSubmit: () => void;
  loading: boolean;
  placeholder?: string;
  /**
   * Reports whether the radio group is showing, so the parent can hide a
   * ⌘↵-submit hint that does not apply to it.
   */
  onChoosingChange?: (choosing: boolean) => void;
}) {
  const hasChoices = choices.length > 0;
  const [mode, setMode] = useState<"choose" | "write">(hasChoices ? "choose" : "write");
  const choosing = hasChoices && mode === "choose";

  useEffect(() => {
    onChoosingChange?.(choosing);
  }, [choosing, onChoosingChange]);

  const switchMode = () => {
    onAnswerChange("");
    setMode((m) => (m === "choose" ? "write" : "choose"));
  };

  return (
    <div className="flex flex-col gap-3">
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
                  name="answer-choice"
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
          placeholder={placeholder}
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
    </div>
  );
}
