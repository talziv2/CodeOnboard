"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import Button from "@/components/ui/Button";
import {
  placeBubble,
  tourSelector,
  TOUR_LENGTH,
  type Rect,
  type TourStep,
} from "@/lib/tour";
import { t } from "@/lib/strings";

/**
 * The spotlight and the bubble: the only part of the tour that touches the DOM.
 *
 * ── HOW THE PAGE IS FROZEN ────────────────────────────────────────────────────
 *
 * Four rectangles, not one overlay with a hole punched in it. The dimmed area is
 * drawn as the four bands above, below, left and right of the target, so the
 * target's own rectangle has no scrim over it: no cloned element, no z-index fight
 * with the app's own overlays. Everything outside is covered and therefore inert,
 * which is the freeze.
 *
 * The hole is only a hole if the CONTAINER lets the pointer through too. A
 * full-viewport root is itself an element under the cursor, and while it was
 * interactive a gated step's click landed on the overlay rather than on the
 * control it was pointing at — the spotlight looked right and did nothing. So the
 * root is `pointer-events-none` and every piece that must stop a click opts back
 * in: the four bands, the bubble, and the blocker below.
 *
 * On a read-only step the hole gets a blocker of its own, because those are the
 * steps where a stray click costs something: clicking a stop in the rail would
 * jump the session out from under the tour.
 *
 * ── WHY IT MEASURES CONTINUOUSLY ──────────────────────────────────────────────
 *
 * The rectangle is re-read on a clock while a step is open. The obvious
 * alternative — measure once, then listen for resize and scroll — is wrong here
 * for a reason specific to this app: the lesson lives in a nested scrollport, the
 * source pane is draggable and resizable, the brief collapses on scroll and the
 * rail has three width bands. Any of those moves a target without firing a
 * listener the overlay could reasonably be bound to. A rect read per tick costs
 * one forced layout and cannot go stale; state is only written when a number
 * actually changes, so a still page renders once and then stops.
 *
 * A target that never appears is reported as missing after a delay rather than
 * immediately, because `entryFix` may still be re-rendering the column the target
 * lives in.
 */

/** How much room the ring leaves around the element it is drawn on. */
const PAD = 6;
/**
 * How long a target may be absent before the step gives up on it.
 *
 * Measured in time rather than frames because the two clocks below do not tick
 * at the same rate, and long enough that `entryFix`'s re-render — which is what
 * puts most targets on screen — is never mistaken for a target that is not there.
 */
const MISSING_AFTER_MS = 600;
/** The slow clock. See `useTargetRect`. */
const POLL_MS = 120;
/** Attempts to bring one target into view before letting it be. */
const MAX_SCROLLS = 4;
const BUBBLE_WIDTH = 320;

function sameRect(a: Rect | null, b: DOMRect): boolean {
  return (
    a !== null &&
    Math.abs(a.x - b.x) < 0.5 &&
    Math.abs(a.y - b.y) < 0.5 &&
    Math.abs(a.width - b.width) < 0.5 &&
    Math.abs(a.height - b.height) < 0.5
  );
}

/**
 * Is the learner being shown a ring around something they cannot see?
 *
 * A FRACTION rather than "fully inside the viewport", because several targets
 * are taller than the viewport by design — the rail, the source pane, the map
 * column — and demanding full visibility would have the tour scrolling to chase
 * something that can never fit. What matters is whether enough of it is on
 * screen to be the thing the bubble is pointing at.
 */
function mostlyHidden(rect: DOMRect): boolean {
  const shown = Math.min(rect.bottom, window.innerHeight) - Math.max(rect.top, 0);
  return shown < Math.min(rect.height, window.innerHeight) * 0.6;
}

/**
 * Is this element actually being displayed?
 *
 * `getBoundingClientRect` is not an answer to that question, and the gap is not
 * academic: the content of a closed `<details>` is hidden, yet Chrome reports a
 * full-size rectangle for it in empty space below the summary. A step aimed at
 * such an element drew its ring around nothing, and then scrolled the page to
 * bring that nothing into view — observed on the lesson's code citations, which
 * are a disclosure in every phase.
 *
 * `checkVisibility` answers it properly (measured: `false` for exactly that
 * element). `opacityProperty` is deliberately off — a target mid-fade is on its
 * way to being visible and must not be declared absent.
 */
function isVisible(el: Element): boolean {
  const check = (el as Element & { checkVisibility?: (options?: object) => boolean })
    .checkVisibility;
  if (typeof check === "function") {
    return check.call(el, {
      checkVisibilityCSS: true,
      contentVisibilityAuto: true,
      opacityProperty: false,
      visibilityProperty: true,
    });
  }
  // Older engines: the coarse version of the same question.
  return el.getClientRects().length > 0;
}

/** Every scrollable box between an element and the document, innermost first. */
function scrollParents(el: Element): HTMLElement[] {
  const found: HTMLElement[] = [];
  for (let p = el.parentElement; p; p = p.parentElement) {
    const overflow = getComputedStyle(p).overflowY;
    if (/(auto|scroll|overlay)/.test(overflow) && p.scrollHeight > p.clientHeight + 1) {
      found.push(p);
    }
  }
  return found;
}

/**
 * Centre an element in each scrollport that contains it, right now.
 *
 * NOT `scrollIntoView`, and this is the fourth thing in this file to lose an
 * animation for the same reason. Even at `behavior: "auto"` the scroll is
 * performed at a rendering opportunity rather than synchronously, so in a
 * document the browser is not painting it does nothing at all — measured, with
 * `scrollTop` unchanged and the element still hundreds of pixels below the fold,
 * while assigning `scrollTop` directly on the same element moved it immediately.
 *
 * Writing `scrollTop` is also the version whose failure mode is benign: the
 * browser clamps it to the scrollable range, so a target that cannot be centred
 * ends up as close as the container allows instead of nowhere.
 */
function centreInView(el: Element) {
  for (const scroller of scrollParents(el)) {
    // Re-measured per scroller: each scroll moves the element for the next one.
    const box = el.getBoundingClientRect();
    const port = scroller.getBoundingClientRect();
    scroller.scrollTop += box.top + box.height / 2 - (port.top + port.height / 2);
  }
}

/**
 * The current step's target rectangle, live.
 *
 * Returns null both while nothing has been found yet and for a step that has no
 * target at all — the caller distinguishes them by the step, which is the thing
 * that knows.
 */
function useTargetRect(step: TourStep, onMissing: () => void): Rect | null {
  const [rect, setRect] = useState<Rect | null>(null);

  // A LAYOUT effect, so the first measurement happens before the browser paints
  // the step: the bubble is placed against a real rectangle from the very first
  // frame instead of appearing centred and then jumping.
  useLayoutEffect(() => {
    setRect(null);
    if (!step.target) return;

    const selector = tourSelector(step.target);
    let lastSeen = performance.now();
    let reported = false;
    let scrolls = 0;

    const measure = () => {
      const el = document.querySelector(selector);
      // Hidden counts as absent. A target that is in the document but not being
      // displayed is not something a spotlight can point at.
      if (!el || !isVisible(el)) {
        // Absent long enough to mean it: the step has nothing to point at, and
        // the tour walks past it rather than dimming the page over nothing.
        if (!reported && performance.now() - lastSeen > MISSING_AFTER_MS) {
          reported = true;
          onMissing();
        }
        return;
      }
      lastSeen = performance.now();
      const box = el.getBoundingClientRect();
      // BRING THE TARGET TO THE LEARNER. The page is frozen, so they cannot
      // scroll to it themselves — a ring below the fold is a spotlight on
      // nothing, and the lesson's citations are exactly that: several screens
      // down a column the tour has just dimmed.
      //
      // Re-checked on every tick rather than done once. The first sighting of an
      // element is not a reliable moment to judge its position: `entryFix` may
      // still be swapping the surface underneath it, the source pane may be
      // opening beside it, and a single early measurement that happened to look
      // fine used to disable the scroll for the whole step. Bounded, so a target
      // that cannot be brought into view does not get chased forever.
      //
      // See `centreInView` for why the scroll is written by hand and instant.
      if (scrolls < MAX_SCROLLS && mostlyHidden(box)) {
        scrolls += 1;
        centreInView(el);
      }
      setRect((current) =>
        sameRect(current, box)
          ? current
          : { x: box.x, y: box.y, width: box.width, height: box.height }
      );
    };

    // TWO CLOCKS, on purpose. The frame loop is the one that matters — it keeps
    // the ring welded to a target that is being scrolled or dragged. But
    // `requestAnimationFrame` does not tick at all in a document the browser is
    // not painting (a background tab, a headless pane), and an overlay whose only
    // clock is frames renders a full-page scrim with no ring and no bubble in
    // exactly that case. The interval is slow, cheap, and always runs.
    measure();
    const poll = window.setInterval(measure, POLL_MS);
    let frame = requestAnimationFrame(function loop() {
      measure();
      frame = requestAnimationFrame(loop);
    });

    return () => {
      window.clearInterval(poll);
      cancelAnimationFrame(frame);
    };
  }, [step, onMissing]);

  return rect;
}

export default function TourOverlay({
  step,
  index,
  armed,
  onNext,
  onBack,
  onSkip,
  onMissing,
}: {
  step: TourStep;
  index: number;
  /** Waiting on the learner: no `Next`, and the target stays clickable. */
  armed: boolean;
  onNext: () => void;
  onBack: () => void;
  onSkip: () => void;
  onMissing: () => void;
}) {
  const missing = useCallback(() => onMissing(), [onMissing]);
  const rect = useTargetRect(step, missing);
  const bubbleRef = useRef<HTMLDivElement>(null);
  const [bubbleHeight, setBubbleHeight] = useState(0);
  const [viewport, setViewport] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const measure = () => {
      setViewport({ width: window.innerWidth, height: window.innerHeight });
      if (bubbleRef.current) setBubbleHeight(bubbleRef.current.offsetHeight);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [step, armed]);

  // The bubble takes focus on every step so a keyboard user is reading the same
  // thing the spotlight is pointing at. It is not a focus TRAP: on a gated step
  // the learner has to be able to reach the real control, and the page behind is
  // already unreachable by pointer.
  useEffect(() => {
    bubbleRef.current?.focus();
  }, [step]);

  const copy = t.tour.steps[step.id] ?? { title: "", body: "" };
  const isFirst = index === 0;
  const isLast = index === TOUR_LENGTH - 1;
  const placement = placeBubble(
    rect,
    { width: BUBBLE_WIDTH, height: bubbleHeight || 200 },
    viewport.width ? viewport : { width: 1280, height: 800 },
    step.target ? step.side : "center"
  );

  // No rectangle yet — the target has not been found this step. The page dims
  // whole and the bubble centres itself until one arrives, which is a fraction of
  // a second at most and is also exactly what a step with no target looks like.
  const hole = rect
    ? {
        x: Math.max(0, rect.x - PAD),
        y: Math.max(0, rect.y - PAD),
        width: rect.width + PAD * 2,
        height: rect.height + PAD * 2,
      }
    : null;

  return (
    // THE ROOT LETS CLICKS THROUGH, and everything that should stop them opts
    // back in below. A full-viewport container is itself an element under the
    // pointer: leaving it interactive means the hole is only visually a hole, and
    // a gated step's click lands on the overlay instead of on the control it is
    // pointing at — measured exactly that way before this line existed.
    <div className="pointer-events-none fixed inset-0 z-[60]" role="presentation">
      {/* ── the freeze ─────────────────────────────────────────────────────── */}
      {hole ? (
        <>
          <div
            className="pointer-events-auto absolute inset-x-0 top-0 bg-scrim"
            style={{ height: hole.y }}
          />
          <div
            className="pointer-events-auto absolute inset-x-0 bottom-0 bg-scrim"
            style={{ top: hole.y + hole.height }}
          />
          <div
            className="pointer-events-auto absolute start-0 bg-scrim"
            style={{ top: hole.y, height: hole.height, width: hole.x }}
          />
          <div
            className="pointer-events-auto absolute end-0 bg-scrim"
            style={{ top: hole.y, height: hole.height, left: hole.x + hole.width }}
          />
          {/* The ring. Never interactive — it would be sitting exactly on top of
              the control the learner is being asked to click. */}
          <div
            aria-hidden
            className="tour-ring pointer-events-none absolute rounded-field"
            style={{ top: hole.y, left: hole.x, width: hole.width, height: hole.height }}
          />
          {/* Read-only steps cover their own hole: the spotlight says "look at
              this", not "click this", and the click it would otherwise invite
              navigates the session away from the tour. */}
          {!armed && (
            <div
              aria-hidden
              className="pointer-events-auto absolute"
              style={{ top: hole.y, left: hole.x, width: hole.width, height: hole.height }}
            />
          )}
        </>
      ) : (
        <div className="pointer-events-auto absolute inset-0 bg-scrim" />
      )}

      {/* ── the bubble ─────────────────────────────────────────────────────── */}
      <div
        ref={bubbleRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="false"
        aria-label={copy.title}
        // IT SNAPS, and that is deliberate. Gliding between steps looks better and
        // was tried: `transition-[top,left]`. But a transition owns the property
        // while it is running, and in a document the browser is not painting it
        // never advances — measured here, `getAnimations()` reporting two live
        // transitions with the element frozen at the previous step's coordinates
        // while the inline style already held the new ones. That is the same trap
        // `globals.css` documents for the `rise` keyframe, and the same rule
        // applies: the stalled state of anything animated here has to be correct.
        // Snapped, the worst case is a bubble that arrives without ceremony.
        className="pointer-events-auto absolute flex flex-col gap-3 rounded-card border border-rule bg-slab p-4 shadow-overlay outline-none"
        style={{ top: placement.top, left: placement.left, width: BUBBLE_WIDTH }}
      >
        <span aria-live="polite" className="sr-only">
          {t.tour.announce(index + 1, TOUR_LENGTH, copy.title)}
        </span>

        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-signal">
            {t.tour.step(index + 1, TOUR_LENGTH)}
          </span>
          <h2 className="font-display text-head font-medium tracking-tight text-chalk">
            {copy.title}
          </h2>
        </div>

        <p className="text-aside text-paper">{copy.body}</p>

        {/* The instruction, and only while the step is actually waiting for it. */}
        {armed && copy.cue && (
          <p className="flex items-center gap-2 font-mono text-meta text-signal">
            <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-signal" />
            {copy.cue}
          </p>
        )}

        {isLast && <p className="text-meta text-graphite">{t.tour.finished}</p>}

        <div className="flex items-center gap-2 pt-0.5">
          {!isFirst && (
            <Button variant="chrome" size="sm" onClick={onBack}>
              {t.tour.back}
            </Button>
          )}
          {/* An armed step has no `Next`: the control it is pointing at is the way
              on. Offering both would make the gate advisory, and the learner would
              never find out what the button does. */}
          {!armed && (
            <Button variant="primary" size="sm" onClick={onNext}>
              {isLast ? t.tour.done : copy.action ?? t.tour.next}
            </Button>
          )}
          <button
            onClick={onSkip}
            className="ms-auto font-mono text-micro text-graphite transition hover:text-signal"
          >
            {isLast ? t.tour.close : t.tour.skip}
          </button>
        </div>
      </div>
    </div>
  );
}
