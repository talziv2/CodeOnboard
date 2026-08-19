"use client";

import { useRef } from "react";

/**
 * A fixed-vocabulary answer, as a list you can drive from the keyboard.
 *
 * The options are not labels — `GOAL_TYPE_MAP` and `CODE_DEPTH_MAP` in
 * `backend/agents/goal/questions.py` are keyed on these exact strings, and the
 * backend refuses anything outside the vocabulary. So the list is the whole
 * input; there is deliberately no free-text box beside it to type an answer that
 * could only be rejected.
 *
 * SELECTING AND CONFIRMING ARE SEPARATE, and that is the whole point of the
 * component. Clicking an option selects it and nothing else — the interview never
 * advances under the pointer, so a misclick costs a correction rather than a
 * question. `↑`/`↓` move the selection, `Enter` confirms it, and the adjacent
 * Continue button does the same thing for anyone who would rather click it. There
 * is no timed auto-advance and no double-click path; both were considered and
 * ruled out, because both make the same promise the click model already breaks —
 * that the user's next input is a commitment they did not ask to make.
 *
 * Semantics are a radio group rather than a listbox: exactly one answer is
 * possible, arrow keys both move and select, and `aria-checked` says which is
 * chosen. Selection is carried by a filled-versus-hollow dot as well as by
 * colour, so it survives a monochrome or colour-blind reading.
 */
export default function OptionList({
  options,
  value,
  onSelect,
  onConfirm,
  disabled = false,
}: {
  options: string[];
  /** The selected option string, or "" for nothing chosen yet. */
  value: string;
  onSelect: (option: string) => void;
  onConfirm: () => void;
  disabled?: boolean;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const current = options.indexOf(value);

  const move = (delta: number) => {
    // From nothing selected, ↓ starts at the top and ↑ at the bottom.
    const from = current < 0 ? (delta > 0 ? -1 : 0) : current;
    const next = (from + delta + options.length) % options.length;
    onSelect(options[next]);
    refs.current[next]?.focus();
  };

  return (
    <div
      role="radiogroup"
      className="flex flex-col gap-1.5"
      onKeyDown={(e) => {
        if (disabled) return;
        if (e.key === "ArrowDown") {
          e.preventDefault();
          move(1);
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          move(-1);
        } else if (e.key === "Enter") {
          // `preventDefault` matters: without it the browser synthesises a click
          // on the focused option, which re-selects it and swallows the confirm,
          // so Enter would silently do nothing on the one path most likely to be
          // used by keyboard.
          e.preventDefault();
          if (value) onConfirm();
        }
      }}
    >
      {options.map((option, i) => {
        const selected = option === value;
        return (
          <button
            key={option}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            // Roving tabindex: one stop for the whole group, so Tab moves past the
            // question rather than through six of them.
            tabIndex={selected || (current < 0 && i === 0) ? 0 : -1}
            // The parent remounts this list per question, so this lands focus on
            // the restored answer when stepping back and on the first option
            // otherwise — which is what makes the interview completable without
            // reaching for Tab between questions. Focus is not selection: nothing
            // is chosen until an arrow key or a click says so.
            autoFocus={selected || (current < 0 && i === 0)}
            disabled={disabled}
            onClick={() => onSelect(option)}
            className={`flex min-h-[calc(44rem/16)] w-full items-center gap-3 rounded-field border px-4 py-2.5 text-start text-aside transition ${
              selected
                ? "border-signal-dim bg-signal/15 text-signal"
                : "border-rule text-paper hover:border-signal-dim hover:text-signal"
            }`}
          >
            <span
              aria-hidden
              className={`h-2 w-2 shrink-0 rounded-full ${
                selected ? "bg-signal" : "border border-rule"
              }`}
            />
            {option}
          </button>
        );
      })}
    </div>
  );
}
