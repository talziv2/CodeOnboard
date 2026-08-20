"use client";

import AnswerTranscript, { type TranscriptEntry } from "@/components/goal/AnswerTranscript";
import Button from "@/components/ui/Button";
import { t } from "@/lib/strings";

/**
 * The gate between the interview and the wait.
 *
 * Everything downstream is decided by these answers — which files get read, what
 * gets taught and in what order — and getting them wrong is not cheap to discover:
 * the next thing that happens is a multi-minute pipeline run, and the mistake only
 * becomes visible in the learning path at the end of it. So the answers are shown
 * back before any of that starts, in one place, and nothing begins until the user
 * says so.
 *
 * This is also the ONLY place the answers are shown. During the interview they stay
 * hidden: a running transcript put the previous answers next to the current
 * question, which turned every question into a re-read of everything already said.
 * Reviewing is a separate act from answering, and it belongs at the end.
 *
 * Two ways backwards, deliberately. `Back` reopens the last question, which is what
 * someone who just mistyped wants. `Change` on a row goes to that specific answer,
 * which is what someone scanning the summary and spotting a wrong one wants —
 * without stepping through everything in between. Both run through the same
 * `/goal/back` unwinding, so the server's rules about clearing the goal type apply
 * either way.
 */
export default function ReviewStep({
  entries,
  onEdit,
  onBack,
  onStart,
  busy = false,
  editable = true,
}: {
  entries: TranscriptEntry[];
  /** Reopen one specific question by its 1-based interview position. */
  onEdit: (index: number) => void;
  /** Reopen the last question. */
  onBack: () => void;
  onStart: () => void;
  busy?: boolean;
  /**
   * False once the goal dialogue is gone from the server. Starting still works —
   * the goal is already in hand and `/session/start` does not need the interview —
   * so the gate stays usable and only the ways backwards disappear.
   */
  editable?: boolean;
}) {
  return (
    <div className="rise flex w-full max-w-xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
          {t.goal.reviewLabel}
        </span>
        <h2 className="font-display text-head font-medium tracking-tight text-chalk text-balance">
          {t.goal.reviewTitle}
        </h2>
        <p className="text-aside text-graphite">{t.goal.reviewNote}</p>
      </div>

      <section className="flex flex-col gap-3">
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
          {t.goal.answers}
        </span>
        <AnswerTranscript
          entries={entries}
          onEdit={onEdit}
          disabled={busy}
          editable={editable}
        />
      </section>

      <div className="flex items-center gap-3">
        <Button variant="primary" size="lg" onClick={onStart} disabled={busy}>
          {busy ? t.goal.thinking : t.goal.startSession}
        </Button>
        {editable && (
          <Button variant="ghost" onClick={onBack} disabled={busy}>
            {t.goal.back}
          </Button>
        )}
      </div>
    </div>
  );
}
