"use client";

import type { NodeGap } from "@/lib/api";
import Button from "@/components/ui/Button";
import { InlineProse } from "@/components/ui/Prose";
import Marker from "@/components/ui/Marker";
import SectionLabel, { BlockTitle } from "@/components/ui/SectionLabel";
import { BLOCK_ICON, LESSON_ICON } from "@/lib/lessonIcons";
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
 * Two verbs per open gap, and the asymmetry is the point — but the LABELS used to
 * hide it. `Clear this` and `Set aside` read as two ways of dismissing the same
 * row, when only one of them is about the gap going away at all:
 *
 *   `Check me on this`  asks for a fresh question about that specific claim. The
 *                       ONLY act that can produce `verified`, and — once the
 *                       two-question cap has stopped `Ask me again` proposing
 *                       this gap — the only remaining route to it at all. So it
 *                       stays an explicit, discoverable button rather than
 *                       becoming a link on the claim text.
 *   `Ignore for now`    records that the learner is deliberately not doing that.
 *                       Never evidence: a waived gap does not permit
 *                       `understood`, the stop stays short of demonstrated, and
 *                       `readiness()` stays honest. What it buys is that the
 *                       system stops asking, and it is reversible.
 *
 * **Ignored is not resolved**, and three things say so rather than one: the
 * status chip (`Ignored for now` against `Resolved`), the colour (muted against
 * jade), and the note under it. The tally counts only `verified` in its
 * numerator, so ignoring a gap moves nothing.
 *
 * The list is chosen by the panel, which prefers the just-graded reply over the
 * graph because the graph lags by one refresh on the warm-up path. That
 * preference stays there; this renders what it is given.
 */

const isOpen = (gap: NodeGap) => (gap.status ?? "open") === "open";

/**
 * THREE STATES, THREE MARKERS, and the third one is the reason this is worth
 * doing at all. `Resolved` and `Ignored for now` are already distinguished by
 * their wording, their colour and the note under them, because a learner reading
 * `Ignored` as `Resolved` would be reading the ledger backwards. The glyph is a
 * fourth channel saying the same thing, and it is deliberately NOT a second
 * tick — see `gapWaived` in `lessonIcons`.
 */
function StatusChip({ gap }: { gap: NodeGap }) {
  if (isOpen(gap)) {
    return (
      <span className="flex items-center gap-1.5">
        <Marker glyph={LESSON_ICON.gapOpen} />
        <span className="text-micro uppercase tracking-wide text-graphite">
          {gap.blocking ? t.lesson.gapBlocking : t.lesson.gapNonBlocking}
        </span>
      </span>
    );
  }
  const verified = gap.status === "verified";
  return (
    <span className="flex items-center gap-1.5">
      <Marker glyph={verified ? LESSON_ICON.gapResolved : LESSON_ICON.gapWaived} />
      <span
        className={`text-micro uppercase tracking-wide ${
          verified ? "text-jade" : "text-muted"
        }`}
      >
        {verified ? t.lesson.gapStatusVerified : t.lesson.gapStatusWaived}
      </span>
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
        {/* Why it settled. A resolved gap earned it; an ignored one was a choice
            the learner can still reverse, and saying so is what keeps `Ignore
            for now` from reading as a dead end — and, just as importantly, from
            reading as a second way of resolving it. */}
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
      {/* A settled gap keeps its row and loses its verbs — except an ignored one,
          which the learner may still decide to be checked on. That asymmetry is
          the state model showing through: `verified` is terminal because it was
          earned, `waived` is a decision and decisions can be revisited. */}
      {!verified && (
        <div className="flex shrink-0 items-center gap-3">
          {/* Bordered against a bare text verb, rather than two buttons of equal
              weight. Asking to be checked and choosing not to are not two
              flavours of the same choice, and the primary solid is reserved for
              the panel's one CTA — a solid on every row would make three gaps
              look like three CTAs. */}
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

/**
 * How loudly the ledger is drawn.
 *
 * `null` is the resting state: a block among blocks. The other two mark it as
 * something that changed BECAUSE OF THE ANSWER JUST GIVEN, and they borrow the
 * arrival notice's palette rather than inventing one — `brass` is already the
 * app's "unsettled, wants attention, is not an error", and `jade` is already
 * "closed or recovered" (see `ui/Callout.tsx`).
 *
 * Border-weighted and faintly washed, exactly as `Callout` does it: the box is
 * marked, not turned into a banner.
 */
type Accent = "opened" | "resolved" | null;

const ACCENT: Record<"opened" | "resolved", { box: string; label: string }> = {
  opened: { box: "border-brass/60 bg-brass/[0.07]", label: "text-brass" },
  resolved: { box: "border-jade/40 bg-jade/10", label: "text-jade" },
};

export default function GapList({
  gaps,
  onSolve,
  onWaive,
  disabled = false,
  solvingGapId = null,
  accent = null,
  note = null,
}: {
  gaps: NodeGap[];
  onSolve: (gapId: string) => void;
  onWaive: (gapId: string) => void;
  disabled?: boolean;
  /** The gap a verification question is currently being written for. */
  solvingGapId?: string | null;
  /**
   * Mark the ledger as changed by the last answer.
   *
   * A DECISION MADE BY THE PANEL, not here: what "just changed" means is a fact
   * about the grading reply, and this component only ever renders what it is
   * given (see the note at the top of the file).
   */
  accent?: Accent;
  /** One line saying what changed. Rendered only alongside an accent. */
  note?: string | null;
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

  const marked = accent ? ACCENT[accent] : null;

  return (
    <div
      className={`flex flex-col gap-3 ${
        marked ? `rounded-card border px-4 py-3 ${marked.box}` : ""
      }`}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        {/* The heading takes the accent's colour so the mark is not carried by
            the border alone — the same pairing `Callout` uses, where the tinted
            eyebrow is what names the box. */}
        {/* The block's own title, so it disappears when the collapsed row above
            has already said it. `Settled` below stays a `SectionLabel`: nothing
            has named that, and it divides the ledger's two halves.

            THE MARKER IS STATE-BLIND ON PURPOSE. `⚠️` marks the LEDGER, not the
            current state — "what you got wrong here" is past tense, and it is a
            record that keeps its rows after they close. Two things follow. The
            live state is reported by the tally beside it and by the count on the
            collapsed row, which are the channels that can move; and the marker
            stays identical on the collapsed row and on this heading, which is
            the agreement `BLOCK_ICON` exists to guarantee — a row that warns
            opening onto a heading that does not is the disagreement, not the
            fix. */}
        <BlockTitle tone={marked ? "raised" : "quiet"} icon={BLOCK_ICON.gaps}>
          <span className={marked?.label}>{t.lesson.gapsHeading}</span>
        </BlockTitle>
        {/* Resolved over total, not a count of what is wrong. The denominator is
            the whole ledger, which is the only reason the numerator can move. */}
        {gaps.length > 0 && (
          <span className="text-micro uppercase tracking-wide text-graphite">
            {t.lesson.gapsTally(resolved, gaps.length)}
          </span>
        )}
      </div>
      {/* WHAT JUST HAPPENED, above the standing explanation of what the list is.
          The learner arriving at an auto-opened ledger needs to know why it
          opened before they need to know how ledgers work. */}
      {marked && note && (
        <p className={`measure text-meta ${marked.label}`}>{note}</p>
      )}
      <p className="text-meta text-graphite">{t.lesson.gapsHelp}</p>

      {open.length > 0 && <ul className="flex flex-col gap-2">{open.map(row)}</ul>}

      {settled.length > 0 && (
        <div className="flex flex-col gap-2">
          {/* NO MARKER, AND THAT IS THE DECISION.
   
              `settled` is `verified` OR `waived`, and the heading is worded
              neutrally precisely because it covers both — so any single glyph
              here picks one of two opposite states and asserts it about the
              other. A ✅ was the first attempt and it was the worst possible
              choice: ignore your only gap and the section read `✅ Settled`
              above a tally saying `0 of 1 resolved` and a row saying `Still
              unresolved — you chose not to work on it now`. The tick is the
              largest, fastest-read thing in that stack, and it said the
              opposite of the two channels under it.
   
              A state-aware glyph was the other option and is worse: it would
              make a learner DECISION render as a change in status, which is
              exactly what waiving must never do. The rows carry their own
              markers — ✅ against 💤 — and that is where the distinction
              belongs, one per row, because it is per row that it is true. */}
          <SectionLabel>{t.lesson.gapSettledHeading}</SectionLabel>
          <ul className="flex flex-col gap-2">{settled.map(row)}</ul>
        </div>
      )}
    </div>
  );
}
