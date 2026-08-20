"use client";

import type { ReactNode } from "react";
import Disclosure from "@/components/ui/Disclosure";
import type { BlockState, LessonBlocks } from "@/lib/lessonView";

/**
 * The canvas, placed by phase rather than by accumulation.
 *
 * `lessonView.lessonBlocks` decides which blocks are open, collapsed or absent;
 * this puts them on screen in that order and at that weight. Two responsibilities,
 * kept apart on purpose: the decision is a pure function with a test per phase, and
 * this file is only placement.
 *
 * ORDER IS PART OF THE ANSWER. The collapsed blocks sit ABOVE the primary artifact
 * and the reveal sits below it, so the primary action is never behind a long-form
 * read — the stranded-primary problem the direction doc's Option B exists to avoid.
 * A learner who has just answered sees, in order: what they were reading (one line,
 * collapsed), the verdict with its key point, and then the explanation.
 */
export default function LessonCanvas({
  blocks,
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
  /** Summary text for each collapsible block, with counts where they help. */
  labels: {
    setup: string;
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
  const show = (state: BlockState, node: ReactNode, collapsed: () => ReactNode) => {
    if (state === "absent") return null;
    return state === "open" ? node : collapsed();
  };

  return (
    <>
      {show(blocks.setup, setup, () => (
        <Disclosure label={labels.setup}>{setup}</Disclosure>
      ))}

      {show(blocks.tracePath, tracePath, () => (
        <Disclosure label={labels.tracePath} count={labels.tracePathCount}>
          {tracePath}
        </Disclosure>
      ))}

      {show(blocks.gaps, gaps, () => (
        <Disclosure label={labels.gaps} count={labels.gapsCount}>
          {gaps}
        </Disclosure>
      ))}

      {show(blocks.attempts, attempts, () => (
        <Disclosure label={labels.attempts} count={labels.attemptsCount}>
          {attempts}
        </Disclosure>
      ))}

      {/* The primary artifact. Exactly one of these two is ever open — asserted in
          `lessonView.test.ts`, which is the single-composer invariant restated as
          information architecture rather than left to render order. */}
      {blocks.question !== "absent" && question}
      {blocks.feedback !== "absent" && feedback}

      {/* Below the primary, always. The actions live inside the feedback card, so
          the explanation can be as long as it needs to be without pushing the
          thing the learner is meant to do next off the screen. */}
      {blocks.reveal !== "absent" && reveal}
    </>
  );
}
