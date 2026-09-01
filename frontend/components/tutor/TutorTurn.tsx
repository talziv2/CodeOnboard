"use client";

import Prose from "@/components/ui/Prose";
import type { TutorCitation, TutorTurn as Turn } from "@/lib/api";
import { t } from "@/lib/strings";

/**
 * One exchange.
 *
 * TWO KINDS OF TEXT, TWO RENDERERS, and the split is a project rule rather than a
 * styling choice (CLAUDE.md, "UI copy"):
 *
 *   the learner's question   `whitespace-pre-wrap`, exactly as typed. Interpreting
 *                            their asterisk as emphasis rewrites what they said.
 *   the Tutor's answer       through `Prose`, because the model writes markdown —
 *                            backticked identifiers throughout, and the occasional
 *                            fence.
 *
 * A HINT HAS NO QUESTION. The learner pressed a control rather than typing, so the
 * turn stores an empty question and this renders the rung instead — showing an
 * empty "You" bubble would imply they said nothing when they asked for help.
 */
export default function TutorTurn({
  turn,
  onCite,
  onPin,
  stale,
}: {
  turn: Turn;
  onCite: (citation: TutorCitation) => void;
  onPin: (turn: Turn) => void;
  /** The turn was asked at a stop that is no longer on the route. */
  stale?: boolean;
}) {
  const isHint = turn.mode === "scaffold" && turn.hint_level > 0 && !turn.question;

  return (
    <li className="flex flex-col gap-2 border-b border-rule/60 pb-4 last:border-b-0">
      {stale && (
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-muted">
          {t.tutor.earlierStop}
        </span>
      )}

      {isHint ? (
        // The rung, WITHOUT the denominator: the ladder below already states
        // "Hint 2 of 3", and printing the cap twice put two copies of one fact on
        // screen — which is also how the test found it, by matching both.
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-signal">
          {t.tutor.hintTurn(turn.hint_level)}
        </span>
      ) : (
        turn.question && (
          <div className="flex flex-col gap-1">
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
              {t.tutor.you}
            </span>
            {/* Never markdown. The one place the learner's own words appear is the
                one place fidelity beats polish. */}
            <p className="whitespace-pre-wrap text-aside text-paper">{turn.question}</p>
          </div>
        )
      )}

      <div className="flex flex-col gap-1.5">
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
          {t.tutor.tutorSaid}
          {turn.scope === "out_of_scope" && (
            <span className="ms-2 text-brass">· {t.tutor.outOfScopeTag}</span>
          )}
        </span>
        <Prose text={turn.answer} size="aside" tone="chalk" />
      </div>

      {turn.citations && turn.citations.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {turn.citations.map((citation) => (
            <li key={`${citation.file}:${citation.line_start}`}>
              {/* A CITATION IS NAVIGATION. An answer that names a location and
                  cannot take the learner there is a worse answer than one that
                  names nothing — so this opens the source pane at the range. */}
              <button
                type="button"
                onClick={() => onCite(citation)}
                className="rounded-field border border-rule px-2 py-0.5 font-mono text-micro text-signal transition hover:border-signal-dim hover:bg-signal/10"
              >
                {citation.symbol ?? citation.file}
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onPin(turn)}
          aria-pressed={turn.pinned}
          className={`font-mono text-micro transition ${
            turn.pinned ? "text-jade" : "text-graphite hover:text-signal"
          }`}
        >
          {turn.pinned ? `✓ ${t.tutor.pinned}` : t.tutor.pin}
        </button>
      </div>
    </li>
  );
}
