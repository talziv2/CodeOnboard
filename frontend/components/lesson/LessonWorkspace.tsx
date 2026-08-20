"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * The frame the lesson lives in: a brief that stays, and a canvas that scrolls.
 *
 * The problem it solves is orientation. Every block in a lesson is otherwise a
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
 * THE BRIEF COLLAPSES ONCE IT IS PINNED. At the top of a lesson the full brief is
 * the right thing. Held at that size for the whole scroll it was too much standing
 * rent: measured at 20.3% of the lesson viewport at the small text size and 28.8%
 * at `xlarge`, which on a 768px laptop is about a third of the reading area.
 * Scrolled, it keeps what orients — the position, the title, and the counters,
 * which are navigation — and gives the rest back. Returning to the top restores it.
 *
 * The transition animates `grid-template-rows` from `1fr` to `0fr` rather than a
 * measured max-height, so nothing has to be measured and no layout read is needed.
 * It is also safe if the animation never runs: expanded is the default and a
 * stalled transition snaps between two correct layouts, rather than leaving content
 * present-but-invisible — the trap the `rise` keyframe hit by animating opacity
 * from zero.
 *
 * THE CANVAS IS CAPPED BUT NOT CENTRED. The lesson column runs from 572px to
 * ~1170px depending on the band, and prose set to 48ch inside a 1170px column
 * leaves the cards and lists around it sprawling to twice the width of the text
 * they belong to — hence the cap. It is left-aligned because the lesson is the
 * column's subject, not a card floating in it, and the brief above is capped to the
 * same width so the two share a left edge.
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
  /** Called with `collapsed`, so the brief decides what it keeps while pinned. */
  brief: (collapsed: boolean) => ReactNode;
  children: ReactNode;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    // Found by overflow rather than by "is it taller than its box", so the lookup
    // does not depend on the lesson having finished rendering.
    let box: HTMLElement | null = root.parentElement;
    while (box) {
      const overflow = getComputedStyle(box).overflowY;
      if (overflow === "auto" || overflow === "scroll") break;
      box = box.parentElement;
    }
    if (!box) return;
    const scroller = box;
    // 32px, not 0: a hair of scroll should not swap the layout. The brief has to be
    // genuinely pinned before shrinking reads as intent rather than as a flinch.
    const read = () => setCollapsed(scroller.scrollTop > 32);
    read();
    scroller.addEventListener("scroll", read, { passive: true });
    return () => scroller.removeEventListener("scroll", read);
  }, []);

  return (
    <div ref={rootRef} className="flex flex-col">
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
        data-collapsed={collapsed ? "true" : "false"}
        className="sticky -top-6 z-10 -mt-6 border-b border-rule bg-ink pb-3 pt-6"
      >
        <div className="w-full max-w-[46rem]">{brief(collapsed)}</div>
      </div>

      <div className="flex w-full max-w-[46rem] flex-col gap-6 pt-6">{children}</div>
    </div>
  );
}
