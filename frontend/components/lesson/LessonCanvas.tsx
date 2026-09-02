"use client";

import type { ReactNode } from "react";
import Disclosure from "@/components/ui/Disclosure";
import type { BlockState, LessonBlocks } from "@/lib/lessonView";
import { surfaceBlocks, type Surface } from "@/lib/lessonSurfaces";
import { BLOCK_ICON } from "@/lib/lessonIcons";

/**
 * The canvas, placed by phase rather than by accumulation — and, under `surfaces`,
 * by purpose as well.
 *
 * `lessonView.lessonBlocks` decides which blocks are open, collapsed or absent;
 * `lessonSurfaces` decides which surface each belongs to; this puts them on screen
 * in that order and at that weight. Three responsibilities, kept apart on purpose:
 * two pure functions with a test per phase, and this file is only placement.
 *
 * ORDER IS PART OF THE ANSWER. The collapsed blocks sit ABOVE the primary artifact
 * and the reveal sits below it, so the primary action is never behind a long-form
 * read — the stranded-primary problem the direction doc's Option B exists to avoid.
 * A learner who has just answered sees, in order: what they were reading (one line,
 * collapsed), the verdict with its key point, and then the explanation.
 *
 * ── One component, two surfaces ────────────────────────────────────────────────
 *
 * With no `surface` it renders every block in one column: this is `next`, unchanged
 * and still live as the thing `surfaces` is measured against.
 *
 * With a `surface` it renders only what that surface holds. Not a second component,
 * because the ordering rule above is the same rule on both — collapsed history
 * above, live artifact next, long-form read below — and two copies of it would
 * drift. What differs per surface is *which* blocks arrive and what the collapsed
 * setup is called, and both of those are data.
 *
 * SEPARATION IS NOT PERMISSION TO EXPAND. The whole risk of splitting is that the
 * accumulation simply moves into Understanding, so the disclosure discipline is
 * unchanged on both sides and is asserted per surface in `lessonSurfaces.test.ts`:
 * Lesson holds exactly one expanded section and Understanding at most two, where the
 * single canvas peaked at four.
 */
export default function LessonCanvas({
  blocks,
  surface,
  labels,
  setup,
  tracePath,
  gaps,
  attempts,
  question,
  questionEcho,
  feedback,
  reveal,
  earlier,
}: {
  blocks: LessonBlocks;
  /** Omit for the single canvas (`next`). Pass one to render that surface only. */
  surface?: Surface;
  /** Summary text for each collapsible block, with counts where they help. */
  labels: {
    setup: string;
    /** What the setup is called in Understanding, where it is only ever consulted. */
    tracePath: string;
    tracePathCount?: number;
    gaps: string;
    gapsCount?: number;
    attempts: string;
    attemptsCount?: number;
    earlier?: string;
    question?: string;
  };
  setup: ReactNode;
  tracePath: ReactNode;
  gaps: ReactNode;
  attempts: ReactNode;
  question: ReactNode;
  /**
   * The question as something to RE-READ: its text, with no composer in it.
   *
   * Rendered in place of `question` when a verdict has superseded it. A separate
   * node rather than the same one, because putting the composer inside a disclosure
   * would mean two textareas in the DOM and the one-composer invariant is the thing
   * L4 exists to guarantee.
   */
  questionEcho?: ReactNode;
  feedback: ReactNode;
  reveal: ReactNode;
  /** Replaced explanations. Absent on the single canvas — see `lessonBlocks`. */
  earlier?: ReactNode;
}) {
  // `surfaceBlocks` applies the surface's own supersession, and downgrades anything
  // mirrored into this surface to `collapsed` — the setup is open in Lesson until the
  // explanation exists, and the code locations are a disclosure wherever they appear.
  const state: Partial<Record<keyof LessonBlocks, BlockState>> = surface
    ? surfaceBlocks(blocks, surface)
    : blocks;
  const at = (block: keyof LessonBlocks) => state[block] ?? "absent";

  const show = (
    block: keyof LessonBlocks,
    node: ReactNode,
    label: string,
    count?: number,
    /** `data-tour` for the collapsed form; the open form carries its own. */
    tour?: string,
    /** Arrive unfolded rather than folded — see the trace path's call below. */
    initiallyOpen?: boolean
  ) => {
    const value = at(block);
    if (value === "absent") return null;
    return value === "open" ? (
      node
    ) : (
      // The marker comes from the block NAME, not from the caller. `labels` is
      // per-surface prose and the glyph is not: a collapsed setup wears the same
      // mark as an expanded one, on either surface, which is what makes the row a
      // folded block rather than a differently named one. Nothing to thread
      // through, and nothing that can be threaded through wrongly.
      <Disclosure
        label={label}
        count={count}
        icon={BLOCK_ICON[block]}
        tour={tour}
        initiallyOpen={initiallyOpen}
      >
        {node}
      </Disclosure>
    );
  };

  return (
    <>
      {/* One label each. The setup appears on one surface only, so it needs no
          per-surface name; the code locations appear on both, but as the same
          reference under the same label — a mirror the learner consults, not a
          second copy of something to read. */}
      {show("setup", setup, labels.setup)}
      {/* THE CODE PATH ARRIVES UNFOLDED, ON THE SURFACE THAT OWNS IT.

          `lessonView` records that opening this was tried and reverted the same
          hour, for two reasons. The first — it took STUDY to five open blocks —
          was about the SINGLE COLUMN, and does not survive the split: Lesson holds
          the prose, this, and the explanation, and the prose and the explanation
          supersede each other. The second — the brief already says where the unit
          lives — holds for a single anchor and not for the case this block is
          named after: the brief carries one location line, never the ordered walk
          through four of them, which is the whole content of "this path crosses
          several places".

          Folded, that walk was a labelled row nobody opened, so the one thing the
          block exists to show was the one thing nobody saw. Unfolded it is still a
          `<details>`: the learner folds it and it stays folded.

          NOT `open`, and not a change to `lessonBlocks`. `open` would render it
          bare with no way to put it away, and the state stays `collapsed` because
          foldable is what it still is — so the R3 cap, which counts `open`, keeps
          measuring what it was written to measure.

          THE OWNING SURFACE ONLY. On Understanding this is a MIRROR, and a mirror
          is never expanded — it is there to be consulted mid-answer, not read.
          Under `next` (no surface) it stays folded too: that build is the baseline
          `surfaces` is measured against, and it is the one where the five-open-
          blocks reason still bites literally. */}
      {show(
        "tracePath",
        tracePath,
        labels.tracePath,
        labels.tracePathCount,
        "code-links",
        surface === "lesson"
      )}
      {show("gaps", gaps, labels.gaps, labels.gapsCount)}
      {show("attempts", attempts, labels.attempts, labels.attemptsCount)}

      {/* The primary artifact. Exactly one of these two is ever OPEN — asserted in
          `lessonView.test.ts`, which is the single-composer invariant restated as
          information architecture rather than left to render order.

          The collapsed case is the question the verdict superseded, and it renders
          `questionEcho` — text, not a composer. Above the verdict, because it is
          what the verdict is about. */}
      {at("question") === "open" && question}
      {at("question") === "collapsed" && questionEcho && (
        <Disclosure label={labels.question ?? ""} icon={BLOCK_ICON.question}>
          {questionEcho}
        </Disclosure>
      )}
      {at("feedback") !== "absent" && feedback}

      {/* Below the primary, always. The actions live inside the feedback card, so
          the explanation can be as long as it needs to be without pushing the
          thing the learner is meant to do next off the screen. */}
      {at("reveal") !== "absent" && reveal}

      {/* Last, and never expanded. Below the current explanation because it is
          older than it, and because a record belongs after the thing it is a record
          of. R3's third mitigation. */}
      {at("earlier") !== "absent" &&
        earlier &&
        show("earlier", earlier, labels.earlier ?? "", undefined)}
    </>
  );
}
