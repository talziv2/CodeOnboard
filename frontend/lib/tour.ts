import type { SessionTab, TabEvent } from "@/lib/surfaceTabs";
import { modeOf } from "@/lib/surfaceTabs";

/**
 * The first-run tour: what it points at, in what order, and the one rule that
 * decides whether a step waits for the learner or waits for a click on `Next`.
 *
 * ── WHY THE MODEL IS HERE AND NOT IN THE OVERLAY ──────────────────────────────
 *
 * A tour is a state machine wearing a spotlight. Everything interesting about it
 * — which step is current, whether it is waiting, what happens when a target is
 * not on screen, where the bubble goes — is decidable without a DOM, and every
 * one of those decisions is a place a tour goes wrong in ways nobody notices
 * until a learner is stuck behind a dimmed screen with nothing to click. So the
 * decisions are pure functions with tests, and `TourOverlay` is left with
 * measuring rectangles and drawing.
 *
 * ── GATED STEPS, AND WHY ONLY SOME ────────────────────────────────────────────
 *
 * A **gated** step names an action and waits: the overlay leaves a hole around
 * the real control, everything else is inert, and the tour advances when it
 * observes the state that action produces (`reached`). It advances on the STATE,
 * not on the click — the tour follows the app rather than simulating it, so a
 * learner who reaches the same state another way is not stranded.
 *
 * Three things are gated — opening the source pane, opening Understanding, and
 * the Route/Learn round trip — because each is reversible, costs nothing, and is
 * genuinely hard to guess. Two things are deliberately NOT gated:
 *
 *   the composer   gating it would spend a real graded attempt on a tutorial
 *   the rail       clicking a stop jumps the session away from the tour
 *
 * For those the hole is covered and the step is read-only. "Make them click
 * everything" is a worse tour than one that knows which clicks are free.
 *
 * ── BACK NEVER RE-ARMS ────────────────────────────────────────────────────────
 *
 * Moving backwards lands on a read-only rendering of the earlier step, whatever
 * that step's gate says. This is the rule that removes every dead end: a gate
 * re-armed on the way back can require a control that the state the learner is
 * now in does not render — "click Understanding" while the column is showing the
 * map — and the learner would be left with a spotlight on nothing and no way on.
 * Going forward again re-arms it, so nothing is lost but the trap.
 */

/** Elements the tour can point at, addressed by `data-tour` rather than by class. */
export type TourTarget =
  | "rail"
  | "brief"
  | "code-links"
  | "source-pane"
  | "composer"
  | "tab-understanding"
  | "mode-route"
  | "mode-learn"
  | "surface"
  | "progress";

/** The attribute a component carries to become a target. */
export function tourSelector(target: TourTarget): string {
  return `[data-tour="${target}"]`;
}

export type TourStepId =
  | "intro"
  | "rail"
  | "brief"
  | "code"
  | "source"
  | "composer"
  | "understanding"
  | "route"
  | "map"
  | "back"
  | "progress";

/** Where the bubble prefers to sit relative to its target. */
export type Side = "center" | "start" | "end" | "top" | "bottom";

/**
 * What the tour is allowed to know about the session.
 *
 * Two fields, and both are things a learner's click changes. Deliberately not the
 * graph, the phase or the node: a tour that reads those would grow steps that
 * depend on what the lesson happens to say, and every one of them would be a step
 * that works on one repository and points at nothing on another.
 */
export interface TourContext {
  readonly tab: SessionTab;
  readonly sourceOpen: boolean;
}

export interface TourStep {
  readonly id: TourStepId;
  /** `null` draws a centred card over a fully dimmed page. */
  readonly target: TourTarget | null;
  readonly side: Side;
  /** Present on gated steps: the state the learner's action must produce. */
  readonly reached?: (ctx: TourContext) => boolean;
}

/**
 * The walk. Eleven steps, in the order the workspace is actually used: where you
 * are, what you are being asked, the code it is anchored to, how you answer, what
 * the answer produced, and only then the session-level views.
 */
export const TOUR_STEPS: readonly TourStep[] = [
  { id: "intro", target: null, side: "center" },
  { id: "rail", target: "rail", side: "end" },
  { id: "brief", target: "brief", side: "bottom" },
  // Gated on the pane being open rather than on the click, so a learner who
  // opens it from `Show source` instead satisfies the same step.
  { id: "code", target: "code-links", side: "end", reached: (c) => c.sourceOpen },
  { id: "source", target: "source-pane", side: "start" },
  // Understanding comes BEFORE the composer because it contains it: the question
  // and the answer box are that surface's blocks, not the lesson's
  // (`lib/lessonSurfaces.ts`). Pointing at the composer first would mean pointing
  // at something the learner cannot see yet.
  {
    id: "understanding",
    target: "tab-understanding",
    side: "bottom",
    reached: (c) => c.tab === "understanding",
  },
  { id: "composer", target: "composer", side: "top" },
  {
    id: "route",
    target: "mode-route",
    side: "bottom",
    reached: (c) => modeOf(c.tab) === "route",
  },
  { id: "map", target: "surface", side: "center" },
  {
    id: "back",
    target: "mode-learn",
    side: "bottom",
    reached: (c) => modeOf(c.tab) === "learn",
  },
  { id: "progress", target: "progress", side: "bottom" },
];

export function stepAt(index: number): TourStep | null {
  return TOUR_STEPS[index] ?? null;
}

/**
 * The one navigation a step is allowed to perform on the learner's behalf: put
 * the column back into the state where this step's target exists.
 *
 * It exists because a tour can be walked backwards and a session cannot be
 * un-navigated. One step sends the learner to Understanding and the next but one
 * sends them to the map; `Back` from either would otherwise spotlight a control
 * that the current view does not render. So a step declares the surface it needs
 * and the host puts it there — which is also why most of the middle of the walk
 * names Lesson, and why the composer names Understanding: each step names the
 * surface its own target lives on.
 *
 * Returns the tab event to dispatch, or null when nothing needs moving. It never
 * fires on the forward walk in the ordinary case, because the previous step left
 * the app exactly where the next one wants it.
 */
export function entryFix(step: TourStep, ctx: TourContext): TabEvent | null {
  const mode = modeOf(ctx.tab);
  switch (step.id) {
    // Lesson's own blocks. `understanding` is here too, and for the same reason
    // inverted: the tab is the thing the learner is about to open, so the step
    // needs it NOT to be selected.
    case "brief":
    case "code":
    case "source":
    case "understanding":
      return ctx.tab === "lesson" ? null : { kind: "picked", tab: "lesson" };

    // The composer is Understanding's, not the lesson's.
    case "composer":
      return ctx.tab === "understanding" ? null : { kind: "picked", tab: "understanding" };

    // A demonstration of leaving Learn cannot start in Route.
    case "route":
      return mode === "route" ? { kind: "switchedMode", mode: "learn" } : null;

    // …and the way back cannot start in Learn.
    case "map":
    case "back":
      return mode === "learn" ? { kind: "switchedMode", mode: "route" } : null;

    case "intro":
    case "rail":
    case "progress":
      return null;
  }
}

export type TourStatus = "running" | "done";

export interface TourState {
  readonly index: number;
  readonly status: TourStatus;
  /** Waiting on the learner: the hole is live and there is no `Next`. */
  readonly armed: boolean;
  /** Which way the last move went, so a skipped target keeps travelling. */
  readonly dir: 1 | -1;
}

export type TourEvent =
  /** `Next`. Only offered when the step is not armed. */
  | { kind: "advance" }
  | { kind: "back" }
  | { kind: "skip" }
  /** The session state changed — the only thing that satisfies a gate. */
  | { kind: "observed"; ctx: TourContext }
  /** This step's target is not in the document, so there is nothing to point at. */
  | { kind: "missing" };

export const TOUR_DONE: TourState = { index: TOUR_STEPS.length, status: "done", armed: false, dir: 1 };

export function startTour(ctx: TourContext): TourState {
  return enter(0, 1, ctx);
}

/**
 * Land on `index`, deciding whether the step waits.
 *
 * `armed` is false on any backward move (see the header note) and false for a
 * gate that the session already satisfies — a learner whose source pane was
 * already open from a previous visit should not be asked to open it, and
 * offering `Next` is the honest reading of "you are already there".
 */
function enter(index: number, dir: 1 | -1, ctx: TourContext): TourState {
  if (index >= TOUR_STEPS.length) return TOUR_DONE;
  const at = Math.max(0, index);
  const step = TOUR_STEPS[at];
  return {
    index: at,
    status: "running",
    armed: dir === 1 && step.reached !== undefined && !step.reached(ctx),
    dir,
  };
}

export function reduceTour(state: TourState, event: TourEvent, ctx: TourContext): TourState {
  if (state.status === "done") return state;
  const step = TOUR_STEPS[state.index];

  switch (event.kind) {
    case "skip":
      return TOUR_DONE;

    // `Next` is not offered while armed, and an event that arrives anyway must
    // not become a second way past a gate — that would make the gate advisory.
    case "advance":
      return state.armed ? state : enter(state.index + 1, 1, ctx);

    case "back":
      // Backing out of the first step is not a way to end the tour: the card
      // there has `Skip`, which says what it does.
      return state.index === 0 ? state : enter(state.index - 1, -1, ctx);

    case "observed":
      return state.armed && step.reached?.(event.ctx)
        ? enter(state.index + 1, 1, event.ctx)
        : state;

    // Keep travelling the way we were going. Forward runs out at the end, which
    // is `done`; backward clamps at the intro, which has no target and so can
    // never itself be missing. Both terminate.
    case "missing":
      return enter(state.index + state.dir, state.dir, ctx);
  }
}

/** Steps with a target, for the "3 of 9" the bubble shows. */
export function stepNumber(index: number): number {
  return index + 1;
}

export const TOUR_LENGTH = TOUR_STEPS.length;

// ── placement ────────────────────────────────────────────────────────────────

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Placement {
  top: number;
  left: number;
  /** Where it actually landed, which is what the arrow is drawn from. */
  side: Side;
}

/** Breathing room between the highlighted element and the bubble. */
const GAP = 14;
/** Never closer to the viewport edge than this. */
const MARGIN = 12;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

/**
 * Where the bubble goes.
 *
 * Tries the step's preferred side, then the opposite one, then anywhere it fits —
 * and if nothing fits, clamps into the viewport rather than rendering off-screen.
 * A bubble half off the edge is the failure mode that makes a tour unusable on a
 * laptop, and it is entirely a geometry problem, so it is solved here where it can
 * be tested at any viewport size without a browser.
 */
export function placeBubble(
  target: Rect | null,
  bubble: { width: number; height: number },
  viewport: { width: number; height: number },
  preferred: Side
): Placement {
  if (!target || preferred === "center") {
    return {
      top: Math.max(MARGIN, (viewport.height - bubble.height) / 2),
      left: Math.max(MARGIN, (viewport.width - bubble.width) / 2),
      side: "center",
    };
  }

  const fits: Record<Exclude<Side, "center">, boolean> = {
    end: target.x + target.width + GAP + bubble.width + MARGIN <= viewport.width,
    start: target.x - GAP - bubble.width - MARGIN >= 0,
    bottom: target.y + target.height + GAP + bubble.height + MARGIN <= viewport.height,
    top: target.y - GAP - bubble.height - MARGIN >= 0,
  };

  const opposite: Record<Exclude<Side, "center">, Exclude<Side, "center">> = {
    end: "start",
    start: "end",
    bottom: "top",
    top: "bottom",
  };

  const order: Exclude<Side, "center">[] = [
    preferred as Exclude<Side, "center">,
    opposite[preferred as Exclude<Side, "center">],
    "bottom",
    "end",
    "top",
    "start",
  ];
  const side = order.find((candidate) => fits[candidate]) ?? preferred;

  // Along the target's own axis the bubble is centred on it; across that axis it
  // sits beside it. Both are then clamped, so the worst case is a bubble pressed
  // against an edge and overlapping its target — visible and usable — rather than
  // one placed correctly outside the screen.
  const centredTop = target.y + target.height / 2 - bubble.height / 2;
  const centredLeft = target.x + target.width / 2 - bubble.width / 2;
  const maxTop = viewport.height - bubble.height - MARGIN;
  const maxLeft = viewport.width - bubble.width - MARGIN;

  switch (side) {
    case "end":
      return {
        top: clamp(centredTop, MARGIN, maxTop),
        left: clamp(target.x + target.width + GAP, MARGIN, maxLeft),
        side,
      };
    case "start":
      return {
        top: clamp(centredTop, MARGIN, maxTop),
        left: clamp(target.x - GAP - bubble.width, MARGIN, maxLeft),
        side,
      };
    case "top":
      return {
        top: clamp(target.y - GAP - bubble.height, MARGIN, maxTop),
        left: clamp(centredLeft, MARGIN, maxLeft),
        side,
      };
    default:
      return {
        top: clamp(target.y + target.height + GAP, MARGIN, maxTop),
        left: clamp(centredLeft, MARGIN, maxLeft),
        side: "bottom",
      };
  }
}
