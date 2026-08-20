"use client";

import type { ReactNode } from "react";
import Disclosure from "@/components/ui/Disclosure";
import type { BlockState, LessonBlocks } from "@/lib/lessonView";
import { surfaceBlocks, type Surface } from "@/lib/lessonSurfaces";

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
  feedback,
  reveal,
}: {
  blocks: LessonBlocks;
  /** Omit for the single canvas (`next`). Pass one to render that surface only. */
  surface?: Surface;
  /** Summary text for each collapsible block, with counts where they help. */
  labels: {
    setup: string;
    /** What the setup is called in Understanding, where it is only ever consulted. */
    setupMirror?: string;
    tracePath: string;
    tracePathCount?: number;
    gaps: string;
    gapsCount?: number;
    attempts: string;
    attemptsCount?: number;
  };
  setup: ReactNode;
  tracePath: ReactNode;
  gaps: ReactNode;
  attempts: ReactNode;
  question: ReactNode;
  feedback: ReactNode;
  reveal: ReactNode;
}) {
  // `surfaceBlocks` applies the surface's own supersession — the setup is open in
  // Lesson until the explanation exists, and never open in Understanding, where it
  // is a reference rather than the material.
  const state: Partial<Record<keyof LessonBlocks, BlockState>> = surface
    ? surfaceBlocks(blocks, surface)
    : blocks;
  const at = (block: keyof LessonBlocks) => state[block] ?? "absent";

  const show = (block: keyof LessonBlocks, node: ReactNode, label: string, count?: number) => {
    const value = at(block);
    if (value === "absent") return null;
    return value === "open" ? (
      node
    ) : (
      <Disclosure label={label} count={count}>
        {node}
      </Disclosure>
    );
  };

  // In Understanding the setup is a reference the learner consults mid-answer, and
  // calling it what Lesson calls it would suggest the material moved here.
  const setupLabel =
    surface === "understanding" ? labels.setupMirror ?? labels.setup : labels.setup;

  return (
    <>
      {show("setup", setup, setupLabel)}
      {show("tracePath", tracePath, labels.tracePath, labels.tracePathCount)}
      {show("gaps", gaps, labels.gaps, labels.gapsCount)}
      {show("attempts", attempts, labels.attempts, labels.attemptsCount)}

      {/* The primary artifact. Exactly one of these two is ever open — asserted in
          `lessonView.test.ts`, which is the single-composer invariant restated as
          information architecture rather than left to render order. */}
      {at("question") !== "absent" && question}
      {at("feedback") !== "absent" && feedback}

      {/* Below the primary, always. The actions live inside the feedback card, so
          the explanation can be as long as it needs to be without pushing the
          thing the learner is meant to do next off the screen. */}
      {at("reveal") !== "absent" && reveal}
    </>
  );
}
