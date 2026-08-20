"use client";

import type { ReactNode } from "react";

/**
 * The frame the lesson lives in: a brief that stays, and a canvas that scrolls.
 *
 * The problem it solves is orientation. Every block in a lesson is currently a
 * sibling in one long column, so the further a learner reads — through the setup,
 * the trace path, the gaps, the history, the practice well, the reveal and its two
 * callouts — the less of the page tells them which stop they are on or what they
 * were meant to be able to say afterwards. The objective, which is the standard
 * their answer is marked against, scrolls away first because it is at the top.
 *
 * So the brief is sticky and the canvas moves under it. `sticky` rather than a
 * separate scroll container on purpose: two nested scrollers is what made the
 * source pane's `scrollIntoView` and `offsetTop` both lie (see `CodeLines`), and
 * one scrollport with a pinned child has neither problem.
 *
 * THE CANVAS IS CAPPED AND CENTRED. The lesson column is between 572px and
 * ~1170px wide depending on the band, and prose set to 48ch inside a 1170px
 * column leaves the cards and lists around it sprawling to twice the width of the
 * text they belong to. Capping the whole canvas keeps the column's contents one
 * shape at every width.
 *
 * L3 adds this frame and removes NOTHING: the counters in the brief are triggers
 * that take you to the inline gap list and history, which are still exactly where
 * they were. That is deliberate — if the frame turns out to be wrong, nothing has
 * been lost, and L4 is where the inline copies give way to what the brief offers.
 */
export default function LessonWorkspace({
  brief,
  children,
}: {
  brief: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col">
      {/*
        `top-0` sticks to the top of the scrollport, which is the padding box of
        the page's scroll container. It needs an opaque background, or the canvas
        reads through it.

        `-top-6` and `-mt-6 pt-6` together cancel that container's `py-6`, and
        none of it is cosmetic. Measured: with a plain `top-0` the brief pinned 24px
        BELOW the scrollport top, leaving a transparent strip that scrolling content
        passed through above the pinned header — padding does not clip, so the
        content really was visible up there.

        The reason is that Chrome resolves sticky offsets against the scroll
        container's CONTENT box, not its padding box, so `top: 0` means "24px down
        from the scrollport" whenever the container has top padding. `-top-6` is
        what actually moves the pin; `-mt-6 pt-6` extends the box upward to fill
        the strip while leaving the brief's own content exactly where it was.

        The horizontal padding needs no bleeding, because the canvas shares the
        same padding box and so never occupies the strips either side.
      */}
      <div
        data-lesson-brief
        className="sticky -top-6 z-10 -mt-6 flex flex-col gap-2 border-b border-rule bg-ink pb-3 pt-6">
        {brief}
      </div>

      <div className="mx-auto flex w-full max-w-[46rem] flex-col gap-6 pt-6">
        {children}
      </div>
    </div>
  );
}
