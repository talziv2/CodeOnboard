import { describe, expect, test } from "vitest";
import {
  entryFix,
  placeBubble,
  reduceTour,
  startTour,
  stepAt,
  TOUR_LENGTH,
  TOUR_STEPS,
  type TourContext,
  type TourState,
} from "@/lib/tour";

/**
 * The tour's state machine, and the geometry that places its bubble.
 *
 * What is worth testing here is not "does step 3 follow step 2" — it is the three
 * properties that decide whether a learner can get stuck behind a dimmed screen:
 *
 *   a gate opens on STATE, and `Next` cannot get past it;
 *   going back never re-arms a gate, so it can never demand a control that the
 *     current view does not render;
 *   a target that is not on screen is walked past, in whichever direction the
 *     learner was travelling, and the walk terminates either way.
 *
 * All three are unreachable from a DOM test and trivial from here, which is the
 * reason the model is a pure module in the first place.
 */

const AT_START: TourContext = { tab: "lesson", sourceOpen: false };
const id = (state: TourState) => stepAt(state.index)?.id ?? null;

/** Whatever this step's gate is waiting for, hand it over. */
function grant(stepId: string, ctx: TourContext): TourContext {
  if (stepId === "code") return { ...ctx, sourceOpen: true };
  if (stepId === "understanding") return { ...ctx, tab: "understanding" };
  if (stepId === "route") return { ...ctx, tab: "map" };
  return { ...ctx, tab: "lesson" };
}

/** Walk forward to a step, satisfying every gate on the way. */
function walkTo(target: string, ctx: TourContext = AT_START): TourState {
  let state = startTour(ctx);
  let live = ctx;
  for (let guard = 0; guard < 40 && id(state) !== target; guard += 1) {
    if (state.armed) {
      // Whatever this gate wants, grant it — the point is to reach `target`.
      const step = TOUR_STEPS[state.index];
      live = grant(step.id, live);
      state = reduceTour(state, { kind: "observed", ctx: live }, live);
    } else {
      state = reduceTour(state, { kind: "advance" }, live);
    }
  }
  return state;
}

describe("the walk", () => {
  test("starts on the intro, which has no target and no gate", () => {
    const state = startTour(AT_START);
    expect(id(state)).toBe("intro");
    expect(state.armed).toBe(false);
    expect(TOUR_STEPS[0].target).toBeNull();
  });

  test("reaches every step in order and ends done", () => {
    let state = startTour(AT_START);
    const seen = [id(state)];
    let ctx = AT_START;
    for (let i = 0; i < TOUR_LENGTH + 5 && state.status === "running"; i += 1) {
      if (state.armed) {
        const step = TOUR_STEPS[state.index];
        ctx = grant(step.id, ctx);
        state = reduceTour(state, { kind: "observed", ctx }, ctx);
      } else {
        state = reduceTour(state, { kind: "advance" }, ctx);
      }
      if (state.status === "running") seen.push(id(state));
    }
    expect(state.status).toBe("done");
    expect(seen).toEqual(TOUR_STEPS.map((s) => s.id));
  });

  test("skip ends it from anywhere", () => {
    const state = reduceTour(walkTo("composer"), { kind: "skip" }, AT_START);
    expect(state.status).toBe("done");
  });

  test("a finished tour ignores everything", () => {
    const done = reduceTour(startTour(AT_START), { kind: "skip" }, AT_START);
    for (const event of [{ kind: "advance" }, { kind: "back" }, { kind: "missing" }] as const) {
      expect(reduceTour(done, event, AT_START)).toBe(done);
    }
  });
});

describe("gates", () => {
  test("a gated step waits, and `Next` does not get past it", () => {
    const state = walkTo("understanding");
    expect(state.armed).toBe(true);
    const pushed = reduceTour(state, { kind: "advance" }, AT_START);
    expect(pushed).toBe(state);
    expect(id(pushed)).toBe("understanding");
  });

  test("the state the learner produces is what opens it", () => {
    const state = walkTo("understanding");
    const ctx: TourContext = { tab: "understanding", sourceOpen: true };
    expect(id(reduceTour(state, { kind: "observed", ctx }, ctx))).toBe("composer");
  });

  test("the wrong state does not", () => {
    const state = walkTo("understanding");
    const ctx: TourContext = { tab: "map", sourceOpen: true };
    expect(reduceTour(state, { kind: "observed", ctx }, ctx)).toBe(state);
  });

  test("a gate the session already satisfies is not armed", () => {
    // The source pane is a persisted preference: a returning learner may arrive
    // with it open, and asking them to open it would be asking for nothing.
    const state = walkTo("code", { tab: "lesson", sourceOpen: true });
    expect(id(state)).toBe("code");
    expect(state.armed).toBe(false);
    expect(id(reduceTour(state, { kind: "advance" }, AT_START))).toBe("source");
  });
});

describe("going back", () => {
  test("never re-arms a gate", () => {
    // The trap this rule removes: `Back` into "click Understanding" while the
    // column is showing the map, where that tab is not rendered at all.
    const inRoute: TourContext = { tab: "map", sourceOpen: true };
    const state = reduceTour(walkTo("map"), { kind: "back" }, inRoute);
    expect(id(state)).toBe("route");
    expect(state.armed).toBe(false);
  });

  test("re-arms on the way forward again", () => {
    const inRoute: TourContext = { tab: "map", sourceOpen: true };
    const back = reduceTour(walkTo("map"), { kind: "back" }, inRoute);
    // Forward from `route` with the column back in Learn, which is what
    // `entryFix` will have done by then.
    const learn: TourContext = { tab: "lesson", sourceOpen: true };
    const forward = reduceTour(back, { kind: "advance" }, learn);
    expect(id(forward)).toBe("map");
    // …and `route` itself arms again when re-entered forwards.
    const rearmed = reduceTour(reduceTour(forward, { kind: "back" }, learn), { kind: "advance" }, learn);
    expect(id(rearmed)).toBe("map");
  });

  test("the first step is the floor — back is not a way out", () => {
    const state = startTour(AT_START);
    expect(reduceTour(state, { kind: "back" }, AT_START)).toEqual(state);
  });
});

describe("a target that is not there", () => {
  test("is walked past in the direction of travel", () => {
    const state = walkTo("rail");
    expect(id(reduceTour(state, { kind: "missing" }, AT_START))).toBe("brief");
  });

  test("keeps going backwards when that is the way we came", () => {
    const back = reduceTour(walkTo("brief"), { kind: "back" }, AT_START);
    expect(id(back)).toBe("rail");
    expect(id(reduceTour(back, { kind: "missing" }, AT_START))).toBe("intro");
  });

  test("terminates in both directions", () => {
    // Every target missing — a very narrow viewport, say — must end the tour
    // rather than spin.
    let state = walkTo("rail");
    for (let i = 0; i < TOUR_LENGTH + 5 && state.status === "running"; i += 1) {
      state = reduceTour(state, { kind: "missing" }, AT_START);
    }
    expect(state.status).toBe("done");

    // Backwards it clamps at the intro, which has no target and so can never
    // itself be reported missing.
    let rewinding = reduceTour(walkTo("brief"), { kind: "back" }, AT_START);
    for (let i = 0; i < 10; i += 1) {
      rewinding = reduceTour(rewinding, { kind: "missing" }, AT_START);
    }
    expect(id(rewinding)).toBe("intro");
  });
});

describe("entryFix", () => {
  const step = (stepId: string) => TOUR_STEPS.find((s) => s.id === stepId)!;

  test("puts the lesson column back for the blocks that live in it", () => {
    const inRoute: TourContext = { tab: "map", sourceOpen: false };
    for (const stepId of ["brief", "code", "source", "understanding"]) {
      expect(entryFix(step(stepId), inRoute)).toEqual({ kind: "picked", tab: "lesson" });
    }
  });

  test("asks for nothing when the column is already right", () => {
    for (const stepId of ["brief", "code", "source", "understanding"]) {
      expect(entryFix(step(stepId), AT_START)).toBeNull();
    }
  });

  // The composer is not a block of the lesson: the question and the answer box
  // belong to Understanding (`lib/lessonSurfaces.ts`), so its step names that
  // surface. Getting this wrong is not a cosmetic slip — it points the spotlight
  // at an element the selected tab does not render.
  test("the composer names Understanding, because that is where it lives", () => {
    expect(entryFix(step("composer"), AT_START)).toEqual({
      kind: "picked",
      tab: "understanding",
    });
    const onIt: TourContext = { tab: "understanding", sourceOpen: false };
    expect(entryFix(step("composer"), onIt)).toBeNull();
  });

  test("the walk never points at a surface it has not opened", () => {
    // Every step's target must live on the surface its own `entryFix` selects.
    const surfaceOf: Record<string, string> = {
      brief: "lesson",
      code: "lesson",
      source: "lesson",
      understanding: "lesson",
      composer: "understanding",
    };
    for (const [stepId, tab] of Object.entries(surfaceOf)) {
      const elsewhere: TourContext = { tab: "analysis", sourceOpen: false };
      expect(entryFix(step(stepId), elsewhere)).toEqual({ kind: "picked", tab });
    }
  });

  test("a demonstration of leaving Learn cannot start in Route", () => {
    const inRoute: TourContext = { tab: "analysis", sourceOpen: false };
    expect(entryFix(step("route"), inRoute)).toEqual({ kind: "switchedMode", mode: "learn" });
    expect(entryFix(step("route"), AT_START)).toBeNull();
  });

  test("…and the way back cannot start in Learn", () => {
    expect(entryFix(step("back"), AT_START)).toEqual({ kind: "switchedMode", mode: "route" });
    expect(entryFix(step("map"), AT_START)).toEqual({ kind: "switchedMode", mode: "route" });
  });

  test("steps that are not about the column move nothing", () => {
    const inRoute: TourContext = { tab: "map", sourceOpen: false };
    for (const stepId of ["intro", "rail", "progress"]) {
      expect(entryFix(step(stepId), inRoute)).toBeNull();
      expect(entryFix(step(stepId), AT_START)).toBeNull();
    }
  });
});

describe("placeBubble", () => {
  const viewport = { width: 1280, height: 800 };
  const bubble = { width: 320, height: 200 };

  test("centres when there is no target", () => {
    const at = placeBubble(null, bubble, viewport, "end");
    expect(at.side).toBe("center");
    expect(at.left).toBe((1280 - 320) / 2);
  });

  test("sits beside the target on the preferred side", () => {
    const at = placeBubble({ x: 0, y: 300, width: 260, height: 200 }, bubble, viewport, "end");
    expect(at.side).toBe("end");
    expect(at.left).toBeGreaterThan(260);
  });

  test("flips to the opposite side when the preferred one will not fit", () => {
    // A rail pinned to the right-hand edge: `end` has nowhere to go.
    const at = placeBubble({ x: 1000, y: 300, width: 280, height: 200 }, bubble, viewport, "end");
    expect(at.side).toBe("start");
    expect(at.left).toBeLessThan(1000);
  });

  test("never places the bubble outside the viewport", () => {
    const corners = [
      { x: 0, y: 0, width: 40, height: 30 },
      { x: 1240, y: 770, width: 40, height: 30 },
      { x: 640, y: 400, width: 0, height: 0 },
    ];
    for (const target of corners) {
      for (const side of ["top", "bottom", "start", "end"] as const) {
        const at = placeBubble(target, bubble, viewport, side);
        expect(at.left).toBeGreaterThanOrEqual(0);
        expect(at.top).toBeGreaterThanOrEqual(0);
        expect(at.left + bubble.width).toBeLessThanOrEqual(viewport.width);
        expect(at.top + bubble.height).toBeLessThanOrEqual(viewport.height);
      }
    }
  });

  test("clamps rather than vanishing when nothing fits at all", () => {
    const tiny = { width: 360, height: 260 };
    const at = placeBubble({ x: 10, y: 10, width: 340, height: 240 }, bubble, tiny, "end");
    expect(at.left).toBeGreaterThanOrEqual(0);
    expect(at.top).toBeGreaterThanOrEqual(0);
  });
});

describe("the copy exists for every step", () => {
  test("no step renders a blank bubble", async () => {
    const { t } = await import("@/lib/strings");
    for (const step of TOUR_STEPS) {
      const copy = t.tour.steps[step.id];
      expect(copy, step.id).toBeDefined();
      expect(copy.title.length).toBeGreaterThan(0);
      expect(copy.body.length).toBeGreaterThan(0);
      // A gated step must say what to do; a read-only one must not, or it would
      // be an instruction with no way to carry it out.
      if (step.reached) expect(copy.cue, step.id).toBeTruthy();
      else expect(copy.cue, step.id).toBeUndefined();
    }
  });
});
