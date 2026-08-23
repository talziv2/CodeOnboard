"use client";

import Button from "@/components/ui/Button";
import StartingProgress from "@/components/StartingProgress";
import { t } from "@/lib/strings";

/**
 * `Start over` re-runs the whole pipeline, and this is the screen that says so.
 *
 * It used to say nothing. The menu item disabled itself, its label changed to
 * "Starting over…", and then the session sat unchanged for two to four minutes
 * while the clone, the survey, the investigation and the planning call all ran
 * again — a wait indistinguishable from a click that did nothing, which is
 * exactly how it was reported. Worse, a run that FAILED reset the label and said
 * nothing at all, so the two outcomes looked the same from the outside.
 *
 * So a restart gets the same surface the first run gets: `StartingProgress`,
 * polling the run's own `progress_id`, streaming real stages and real file reads
 * (backend/pipeline/progress.py). Nothing here is a simulation of progress.
 *
 * Two things it does that the landing page's copy does not need to:
 *
 *   - It says the current session is untouched. The learner is standing IN the
 *     thing being replaced, and "what happens to my work" is the only question a
 *     three-minute modal has to answer.
 *   - It offers a way out. The run cannot be stopped — the backend finishes and
 *     writes a session either way — so the button withdraws the WAIT and says
 *     that in its wording, rather than claiming a cancel it cannot perform.
 *
 * A full cover rather than a panel: the session behind it is about to be
 * replaced, and leaving it interactive would invite answering a question on a
 * stop that is being thrown away.
 */
export default function RestartingOverlay({
  repoUrl,
  goal,
  progressId,
  error,
  onRetry,
  onDismiss,
}: {
  repoUrl: string;
  goal: Record<string, string>;
  /** The id this restart's /session/start was sent with. */
  progressId: string;
  /** Set once the run has failed; until then this is the waiting state. */
  error: string | null;
  onRetry: () => void;
  onDismiss: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={error ? t.session.restartFailed : t.session.restartLabel}
      className="fixed inset-0 z-[90] flex flex-col items-center justify-center gap-6 overflow-y-auto bg-ink/95 px-6 py-16 backdrop-blur-sm"
    >
      {error ? (
        <div className="flex w-full max-w-md flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-rust">
              {t.session.restartFailed}
            </span>
            <h2 className="font-display text-head font-medium tracking-tight text-chalk">
              {repoUrl.replace(/^https?:\/\/github\.com\//, "")}
            </h2>
            <p className="measure text-aside text-graphite">
              {t.session.restartReassurance}
            </p>
          </div>

          <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words rounded-field border border-rule bg-trench p-3 font-mono text-micro text-rust">
            {error}
          </pre>

          <div className="flex flex-wrap gap-3">
            <Button variant="primary" size="md" onClick={onRetry}>
              {t.session.restartRetry}
            </Button>
            <Button variant="secondary" size="md" onClick={onDismiss}>
              {t.session.restartCancel}
            </Button>
          </div>
        </div>
      ) : (
        <>
          <StartingProgress
            repoUrl={repoUrl}
            progressId={progressId}
            goal={goal}
            label={t.session.restartLabel}
          />

          <div className="flex w-full max-w-md flex-col gap-3 border-t border-rule pt-4">
            <p className="measure text-meta text-graphite">{t.session.restartNote}</p>
            <div>
              <Button variant="chrome" size="sm" onClick={onDismiss}>
                {t.session.restartCancel}
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
