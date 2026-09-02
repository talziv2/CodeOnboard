"use client";

import type { ArrivalNotice as Notice } from "@/lib/arrival";
import Button from "@/components/ui/Button";
import Callout from "@/components/ui/Callout";
import { LESSON_ICON } from "@/lib/lessonIcons";
import { t } from "@/lib/strings";

/**
 * Says, on the stop itself, that the learner did not walk here.
 *
 * ── What this is for ─────────────────────────────────────────────────────────
 *
 * Jumping stays unconditional: no stop is locked, dependencies are not enforced,
 * and nothing here warns that anything will go wrong. The problem it fixes is
 * that departing from the route used to be completely silent — the rail's order
 * was never mentioned at the one moment it stopped being followed, which is what
 * made the map read as decoration.
 *
 * The tone is `brass` — the palette's yellow. Not `signal`, which would compete
 * with the lesson's own callouts, and not `rust`, which would read as an error:
 * being off the route is neither a verdict about understanding nor a fault. It is
 * the one thing on the page the learner should register before reading what is
 * under it, which is what the marked border is for.
 *
 * ── Draws only ───────────────────────────────────────────────────────────────
 *
 * Every decision — direction, position, whether a number may be quoted at all,
 * whether to show anything — is in `lib/arrival.ts`. This picks a sentence and
 * renders two actions.
 */
export default function ArrivalNotice({
  notice,
  onReturn,
  onDismiss,
  returning = false,
}: {
  notice: Notice;
  /** Rejoin the route: a jump back, recorded as a return rather than a departure. */
  onReturn: (nodeId: string) => void;
  onDismiss: () => void;
  returning?: boolean;
}) {
  // A stop the rail does not number gets a phrase instead of a position, because
  // "stop 3 of 4" above three visible stops is a promise the rail breaks.
  const place = notice.isStation
    ? t.lesson.arrival.place(notice.position, notice.total)
    : t.lesson.arrival.placeAside;

  const sentence =
    notice.direction === "ahead"
      ? t.lesson.arrival.ahead(place, notice.passed)
      : notice.direction === "back"
        ? t.lesson.arrival.back(place, notice.revisited)
        : t.lesson.arrival.here(place);

  return (
    <Callout tone="brass" label={t.lesson.arrival.label} icon={LESSON_ICON.offRoute}>
      <p className="measure text-meta text-paper">{sentence}</p>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        {/* Offered only when the stop they left still exists — see `returnTo` in
            lib/arrival.ts. A button that cannot say where it goes is worse than
            no button. */}
        {notice.returnTo && (
          <Button
            variant="secondary"
            size="xs"
            onClick={() => onReturn(notice.returnTo!.nodeId)}
            disabled={returning}
          >
            {returning
              ? t.lesson.arrival.returning
              : t.lesson.arrival.returnTo(notice.returnTo.title)}
          </Button>
        )}
        <Button variant="ghost" onClick={onDismiss}>
          {t.lesson.arrival.dismiss}
        </Button>
      </div>
    </Callout>
  );
}
