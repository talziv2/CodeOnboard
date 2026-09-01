"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import Prose from "@/components/ui/Prose";
import type { TutorMode } from "@/lib/api";
import { t } from "@/lib/strings";

/**
 * The two controls a learner has while a question is open: another hint, or the
 * answer.
 *
 * ── THE REVEAL IS A DISCLOSED TRADE, NOT A BUTTON WITH A CONSEQUENCE ──────────
 *
 * Pressing it means the current question stops being their assessment and they
 * get a fresh one. That is a legitimate choice and it is theirs — but a
 * consequence disclosed AFTER the fact is not a choice, so:
 *
 *   - the warning is rendered BEFORE the destructive control, not in a toast
 *     afterwards;
 *   - the control's own label carries the whole trade — `Show answer & get a new
 *     question`, never `Show answer`;
 *   - it takes two presses. The first opens the disclosure, the second acts, and
 *     `Keep trying` is beside it at equal weight.
 *
 * ── THE LADDER BOUNDS HINTS, NOT HONESTY ──────────────────────────────────────
 *
 * `can_reveal` is true from rung zero, and that is the server's decision (see
 * `mode.py`). A learner who already knows they want the explanation should not
 * have to climb three rungs to ask for it. What the ladder bounds is how many
 * hints the system will WRITE.
 */
export default function HintLadder({
  mode,
  busy,
  onHint,
  onReveal,
}: {
  mode: TutorMode;
  busy: boolean;
  onHint: () => void;
  onReveal: () => void;
}) {
  const [confirming, setConfirming] = useState(false);

  if (mode.revealed) {
    return (
      <div className="shrink-0 border-t border-rule bg-brass/5 px-3.5 py-2.5">
        <p className="text-meta text-paper">{t.tutor.revealedNotice}</p>
      </div>
    );
  }

  return (
    <div className="flex shrink-0 flex-col gap-2 border-t border-rule px-3.5 py-2.5">
      {confirming ? (
        <div className="flex flex-col gap-2.5">
          {/* THE CONSEQUENCE, BEFORE THE CONTROL. */}
          <p role="alert" className="text-meta text-brass">
            {t.tutor.revealWarning}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="sm" onClick={onReveal} disabled={busy}>
              {t.tutor.revealAction}
            </Button>
            <Button variant="chrome" size="sm" onClick={() => setConfirming(false)}>
              {t.tutor.revealCancel}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          {mode.can_hint ? (
            <Button variant="secondary" size="sm" onClick={onHint} disabled={busy}>
              {mode.hints_used === 0 ? t.tutor.askForHint : t.tutor.askForAnotherHint}
            </Button>
          ) : (
            <span className="text-meta text-graphite">{t.tutor.hintsSpent}</span>
          )}
          {mode.can_reveal && (
            <Button variant="chrome" size="sm" onClick={() => setConfirming(true)}>
              {t.tutor.revealAction}
            </Button>
          )}
          {mode.hints_used > 0 && (
            <span className="ms-auto font-mono text-micro text-signal">
              {t.tutor.hintLevel(mode.hints_used, mode.hints_used + mode.hints_left)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/** The explanation, once it has been paid for. */
export function RevealedExplanation({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-panel border border-brass/40 bg-brass/5 p-3">
      <span className="font-mono text-micro uppercase tracking-[0.14em] text-brass">
        {t.tutor.revealHeading}
      </span>
      <Prose text={text} size="aside" tone="chalk" />
    </div>
  );
}
