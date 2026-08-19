"use client";

import { t } from "@/lib/strings";

export interface TranscriptEntry {
  /** 1-based interview position, so `✎` knows how far back to step. */
  index: number;
  question: string;
  answer: string;
}

/**
 * What you have already said, kept on screen.
 *
 * The interview used to show one question at a time with no record of the rest,
 * which made `Back` the only way to check an earlier answer — and checking it
 * meant leaving the question you were on. Collapsed answers cost four lines and
 * remove the need to navigate to remember.
 *
 * `✎` does not need a new endpoint. `/goal/back` un-answers the last question and
 * hands it back with what was said, so stepping to question 2 from question 5 is
 * three calls to the endpoint that already exists (`GoalDialogue.jumpTo`). That
 * also keeps the backend's ownership of the consequences intact: it is `goalBack`
 * that clears `goal_type` when you cross question 2, which is what makes the
 * follow-ups recompute instead of stranding answers to questions that no longer
 * apply.
 *
 * The entries are held locally rather than fetched. The backend has no
 * "transcript" concept and adding one would be a schema change to display
 * something the client already knows.
 */
export default function AnswerTranscript({
  entries,
  onEdit,
  disabled = false,
}: {
  entries: TranscriptEntry[];
  onEdit: (index: number) => void;
  disabled?: boolean;
}) {
  if (entries.length === 0) return null;

  return (
    <ol className="flex flex-col gap-2.5">
      {entries.map((entry) => (
        <li key={entry.index} className="flex items-start gap-3">
          <span className="mt-[3px] shrink-0 font-mono text-micro text-graphite">
            {entry.index}
          </span>
          <span className="flex min-w-0 flex-col gap-0.5">
            <span className="text-micro text-graphite">{entry.question}</span>
            <span className="text-meta text-paper">{entry.answer}</span>
          </span>
          <button
            type="button"
            onClick={() => onEdit(entry.index)}
            disabled={disabled}
            // The glyph alone is not a name. The accessible label says which
            // answer this changes, because five identical "edit" buttons in a row
            // are five identical announcements.
            aria-label={t.goal.editAnswer(entry.question)}
            className="ms-auto shrink-0 font-mono text-micro text-graphite transition hover:text-signal"
          >
            {t.goal.edit}
          </button>
        </li>
      ))}
    </ol>
  );
}
