"use client";

import type { NodeGap } from "@/lib/api";
import Button from "@/components/ui/Button";
import { InlineProse } from "@/components/ui/Prose";
import SectionLabel from "@/components/ui/SectionLabel";
import { t } from "@/lib/strings";

/**
 * What the learner got wrong here, by name — and what they have since put right.
 *
 * §18.10 calls this the product's most honest surface: it says what is missing
 * rather than how much. Named, not counted — a count says how much is wrong, and
 * only the claim says what.
 *
 * THIS IS A LEDGER, NOT A DEBT COLUMN. It used to render open gaps only, which
 * meant the one thing a learner can actually do about a gap — close it — made
 * the row vanish. The work disappeared at the moment it succeeded, and the only
 * trace was a feedback card that itself cleared on the next action. So a settled
 * gap keeps its row: struck through, dimmed, under `Settled`, with the reason it
 * settled. Progress here is `resolved of total`, which can only be read off a
 * list that keeps both halves.
 *
 * Two verbs per open gap, and the asymmetry is the point. `Clear this` asks for
 * a fresh question about that specific claim — the only act that can produce
 * `verified`. `Set aside` stops the system asking and is never evidence, so a
 * waived gap reads as settled-by-choice, never as resolved.
 *
 * The list is chosen by the panel, which prefers the just-graded reply over the
 * graph because the graph lags by one refresh on the warm-up path. That
 * preference stays there; this renders what it is given.
 */

const isOpen = (gap: NodeGap) => (gap.status ?? "open") === "open";

function StatusChip({ gap }: { gap: NodeGap }) {
  if (isOpen(gap)) {
    return (
      <span className="text-micro uppercase tracking-wide text-graphite">
        {gap.blocking ? t.lesson.gapBlocking : t.lesson.gapNonBlocking}
      </span>
    );
  }
  const verified = gap.status === "verified";
  return (
    <span
      className={`text-micro uppercase tracking-wide ${
        verified ? "text-jade" : "text-muted"
      }`}
    >
      {verified ? t.lesson.gapStatusVerified : t.lesson.gapStatusWaived}
    </span>
  );
}

function GapRow({
  gap,
  onSolve,
  onWaive,
  disabled,
  solving,
}: {
  gap: NodeGap;
  onSolve: (gapId: string) => void;
  onWaive: (gapId: string) => void;
  disabled: boolean;
  solving: boolean;
}) {
  const open = isOpen(gap);
  const verified = gap.status === "verified";
  return (
    <li
      className={`flex items-start justify-between gap-3 rounded-card border px-3 py-2 ${
        open ? "border-rule bg-slab" : "border-rule/50 bg-slab/50"
      }`}
    >
      <div className="flex min-w-0 flex-col gap-1">
        <span
          className={`text-aside ${
            open
              ? "text-chalk"
              : verified
                ? "text-paper line-through decoration-jade/60"
                : "text-graphite line-through decoration-rule"
          }`}
        >
          <InlineProse text={gap.claim} tone="paper" />
        </span>
        <StatusChip gap={gap} />
        {/* Why it settled. A resolved gap earned it; a waived one was a choice
            the learner can still reverse, and saying so is what keeps `Set
            aside` from reading as a dead end. */}
        {!open && (
          <span className="text-micro text-muted">
            {verified ? t.lesson.gapResolvedNote : t.lesson.gapWaivedNote}
          </span>
        )}
        {/* The system has stopped proposing for this one; the learner has not
            run out of chances. Said plainly so the still-live button is not
            mistaken for one the cap should have disabled. */}
        {open && gap.exhausted && (
          <span className="text-micro text-muted">{t.lesson.gapAskedTwice}</span>
        )}
      </div>
      {/* A settled gap keeps its row and loses its verbs — except a waived one,
          which the learner may still decide to clear. */}
      {!verified && (
        <div className="flex shrink-0 items-center gap-3">
          {/* Bordered against a bare text verb, rather than two buttons of equal
              weight. Clearing a gap and giving up on it are not two flavours of
              the same choice, and the primary solid is reserved for the panel's
              one CTA — a solid on every row would make three gaps look like
              three CTAs. */}
          <Button
            variant="secondary"
            size="xs"
            onClick={() => onSolve(gap.id)}
            disabled={disabled}
          >
            {solving ? t.lesson.gapSolveBusy : t.lesson.gapSolve}
          </Button>
          {open && (
            <Button variant="ghost" onClick={() => onWaive(gap.id)} disabled={disabled}>
              {t.lesson.waiveOne}
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

export default function GapList({
  gaps,
  onSolve,
  onWaive,
  disabled = false,
  solvingGapId = null,
}: {
  gaps: NodeGap[];
  onSolve: (gapId: string) => void;
  onWaive: (gapId: string) => void;
  disabled?: boolean;
  /** The gap a verification question is currently being written for. */
  solvingGapId?: string | null;
}) {
  const open = gaps.filter(isOpen);
  const settled = gaps.filter((gap) => !isOpen(gap));
  const resolved = settled.filter((gap) => gap.status === "verified").length;

  const row = (gap: NodeGap) => (
    <GapRow
      key={gap.id}
      gap={gap}
      onSolve={onSolve}
      onWaive={onWaive}
      disabled={disabled}
      solving={solvingGapId === gap.id}
    />
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <SectionLabel>{t.lesson.gapsHeading}</SectionLabel>
        {/* Resolved over total, not a count of what is wrong. The denominator is
            the whole ledger, which is the only reason the numerator can move. */}
        {gaps.length > 0 && (
          <span className="text-micro uppercase tracking-wide text-graphite">
            {t.lesson.gapsTally(resolved, gaps.length)}
          </span>
        )}
      </div>
      <p className="text-meta text-graphite">{t.lesson.gapsHelp}</p>

      {open.length > 0 && <ul className="flex flex-col gap-2">{open.map(row)}</ul>}

      {settled.length > 0 && (
        <div className="flex flex-col gap-2">
          <SectionLabel>{t.lesson.gapSettledHeading}</SectionLabel>
          <ul className="flex flex-col gap-2">{settled.map(row)}</ul>
        </div>
      )}
    </div>
  );
}
