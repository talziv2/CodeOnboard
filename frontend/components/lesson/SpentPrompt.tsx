"use client";

import type { RetryOffer } from "@/lib/api";
import Button from "@/components/ui/Button";
import Prose from "@/components/ui/Prose";
import { t } from "@/lib/strings";

/**
 * The unit's own question, after it has been answered — shown, not answerable.
 *
 * ── The back door this closes ─────────────────────────────────────────────────
 *
 * `revealed` in the panel is `Boolean(result) || attempts.length > 0`, so a
 * revisit to a graded stop returned phase `STUDY` with the composer open and the
 * explanation on the other tab. Answering there is a memory check — exactly what
 * §18.7 removed the "Try again" button to prevent — and it produced a real
 * assessment that could move the stop to `understood`.
 *
 * So the rule was enforced against the learner who read the action row and not
 * against the one who navigated away and came back. **A rule that holds for the
 * learner who reads the interface and not for the one who wanders is not a rule.**
 *
 * ── Why the question stays on screen ──────────────────────────────────────────
 *
 * Removing it entirely was the other option and it is worse. The question is what
 * the explanation above is an explanation OF; a stop that shows a reveal with no
 * question is a page of answers to something unstated. It stays, plainly marked
 * as answered, with the one route to new evidence beside it.
 *
 * The route is `Ask me again`, and it is the same control the verdict card
 * offers — the learner should meet one retry in this session, not two that behave
 * differently depending on which screen they are looking at.
 */
export default function SpentPrompt({
  prompt,
  retry,
  busy,
  onAskAgain,
}: {
  prompt: string;
  /** Absent against a pre-M2 backend; then there is nothing to offer. */
  retry?: RetryOffer;
  busy: boolean;
  onAskAgain: () => void;
}) {
  const reason = retry && !retry.available ? t.lesson.retryReason[retry.reason] : null;

  return (
    <div className="flex flex-col gap-3">
      <Prose text={prompt} size="aside" tone="graphite" />

      <p className="measure border-s-2 border-rule ps-3 text-meta text-graphite">
        {t.lesson.promptAnswered}
      </p>

      {retry?.available && (
        <div>
          <Button variant="primary" size="md" onClick={onAskAgain} disabled={busy}>
            {busy ? t.lesson.askAgainBusy : t.lesson.askAgain}
          </Button>
        </div>
      )}

      {/* Why not, when not. A control that is simply absent leaves the learner
          unable to tell "nothing left to do here" from "something is broken". */}
      {reason && <p className="measure text-meta text-graphite">{reason}</p>}
    </div>
  );
}
