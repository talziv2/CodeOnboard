import { describe, expect, test } from "vitest";
import type { LessonPhase } from "@/lib/lessonPhase";
import {
  activeTab,
  INITIAL_TABS,
  modeOf,
  modesIn,
  reduceTabs,
  surfaceForTab,
  tabsFor,
  tabsInMode,
  type SessionTab,
  type TabEvent,
  type TabState,
} from "@/lib/surfaceTabs";

/**
 * The selection model: two modes, their tabs, and R5.
 *
 * R5 is the risk that the phase model starts driving navigation. The strongest
 * assertion available is not a test at all — `TabEvent` has no phase in it and
 * `reduceTabs` takes no phase, so a phase cannot reach the decision. What the tests
 * add is the rest: that every event does what it claims, that no event can land on a
 * tab this build does not render, that a mode remembers where the learner was, and
 * that the phase-free property is checked rather than merely intended.
 */

const ALL: SessionTab[] = ["lesson", "understanding", "map", "analysis"];
/** With a chapter overview open — Understanding has nothing to show. */
const NO_UNDERSTANDING: SessionTab[] = ["lesson", "map", "analysis"];
/** The comparison build. No modes, two tabs. */
const NEXT: SessionTab[] = ["lesson", "map"];

const EVENTS: TabEvent[] = [
  { kind: "picked", tab: "lesson" },
  { kind: "picked", tab: "understanding" },
  { kind: "picked", tab: "map" },
  { kind: "picked", tab: "analysis" },
  { kind: "switchedMode", mode: "learn" },
  { kind: "switchedMode", mode: "route" },
  { kind: "arrivedAtStop" },
  { kind: "openedSection" },
  { kind: "expandedMap" },
  { kind: "dismissedRoute" },
];

/** Every reachable state, for the "total function" sweeps below. */
const STATES: TabState[] = (["learn", "route"] as const).flatMap((mode) =>
  (["lesson", "understanding"] as const).flatMap((learn) =>
    (["map", "analysis"] as const).map((route) => ({ mode, learn, route }))
  )
);

const at = (state: TabState, available: SessionTab[] = ALL) => activeTab(state, available);

describe("which tabs a build offers", () => {
  test("surfaces gets four, across two modes", () => {
    expect(tabsFor("surfaces")).toEqual(["lesson", "understanding", "map", "analysis"]);
    expect(tabsInMode(tabsFor("surfaces"), "learn")).toEqual(["lesson", "understanding"]);
    expect(tabsInMode(tabsFor("surfaces"), "route")).toEqual(["map", "analysis"]);
  });

  test("next keeps the two it had, and therefore one tab per mode", () => {
    // `legacy` used to be asserted here too. The renderer is gone (L5), so the
    // value no longer exists to ask about. `next` gets no mode switch — see the
    // bar's own suite — because two modes of one tab each decide nothing.
    expect(tabsFor("next")).toEqual(["lesson", "map"]);
    expect(tabsInMode(NEXT, "learn")).toEqual(["lesson"]);
    expect(tabsInMode(NEXT, "route")).toEqual(["map"]);
  });

  test("every tab belongs to exactly one mode, and both modes are inhabited", () => {
    expect(ALL.map(modeOf)).toEqual(["learn", "learn", "route", "route"]);
    expect(modesIn(ALL)).toEqual(["learn", "route"]);
  });

  test("a mode with no offered tabs is not a place", () => {
    expect(modesIn(["lesson", "understanding"])).toEqual(["learn"]);
    expect(modesIn(["map"])).toEqual(["route"]);
  });
});

describe("R5 · a phase can never move the selection", () => {
  test("no event in the union mentions a phase", () => {
    // The type already guarantees it. This asserts the shape a future edit would
    // have to break on purpose: an event carrying `phase`, `result` or `lesson`.
    for (const event of EVENTS) {
      expect(
        Object.keys(event).every((k) => k === "kind" || k === "tab" || k === "mode")
      ).toBe(true);
    }
  });

  test("the same event from the same state is the same answer, whatever the phase", () => {
    // `reduceTabs` has no phase parameter, so this is a property of its signature.
    // Written out anyway, over all four phases, because the claim the design makes
    // is behavioural — "submitting an answer does not switch tabs" — and this is
    // the closest a pure test comes to it.
    const phases: LessonPhase[] = ["STUDY", "FEEDBACK", "VERIFY", "RESOLVED"];
    for (const from of STATES) {
      for (const event of EVENTS) {
        const answers = phases.map(() => JSON.stringify(reduceTabs(from, event, ALL)));
        expect(new Set(answers).size, `${JSON.stringify(from)} + ${event.kind}`).toBe(1);
      }
    }
  });

  test("with no event, nothing moves", () => {
    // There is no "phase changed" event to fire, which is the point: the only way
    // to not move is to have nothing to call.
    for (const from of STATES) {
      const here = at(from);
      expect(at(reduceTabs(from, { kind: "picked", tab: here }, ALL))).toBe(here);
    }
  });
});

describe("what each event does", () => {
  test("picking a tab selects it, and enters its mode", () => {
    const understanding = reduceTabs(INITIAL_TABS, { kind: "picked", tab: "understanding" }, ALL);
    expect(at(understanding)).toBe("understanding");
    expect(understanding.mode).toBe("learn");

    const analysis = reduceTabs(understanding, { kind: "picked", tab: "analysis" }, ALL);
    expect(at(analysis)).toBe("analysis");
    expect(analysis.mode).toBe("route");
  });

  test("picking a tab this build does not render changes nothing", () => {
    // Under `next` there is no Understanding. A stale event naming it must be
    // ignored rather than blanking the column.
    const state = reduceTabs(INITIAL_TABS, { kind: "picked", tab: "understanding" }, NEXT);
    expect(state).toEqual(INITIAL_TABS);
    expect(at(state, NEXT)).toBe("lesson");
  });

  test("switching mode comes back to the tab that mode had open", () => {
    // The whole reason the state is a record. A learner reading their verdict who
    // glances at the map must not be dropped on Lesson when they come back.
    let state = reduceTabs(INITIAL_TABS, { kind: "picked", tab: "understanding" }, ALL);
    state = reduceTabs(state, { kind: "picked", tab: "analysis" }, ALL);
    state = reduceTabs(state, { kind: "switchedMode", mode: "learn" }, ALL);
    expect(at(state)).toBe("understanding");
    state = reduceTabs(state, { kind: "switchedMode", mode: "route" }, ALL);
    expect(at(state)).toBe("analysis");
  });

  test("switching to a mode with nothing in it changes nothing", () => {
    const state = reduceTabs(INITIAL_TABS, { kind: "switchedMode", mode: "route" }, [
      "lesson",
      "understanding",
    ]);
    expect(state).toEqual(INITIAL_TABS);
  });

  test("switching to the mode you are in is a no-op, not a reset", () => {
    const state = reduceTabs(INITIAL_TABS, { kind: "picked", tab: "understanding" }, ALL);
    expect(reduceTabs(state, { kind: "switchedMode", mode: "learn" }, ALL)).toEqual(state);
  });

  test("arriving at a different stop returns to Learn · Lesson, from anywhere", () => {
    // Not a phase transition — the learner navigated. Landing on a new stop showing
    // the previous stop's Understanding, its verdict and gaps gone, would be showing
    // them an empty room.
    for (const from of STATES) {
      const state = reduceTabs(from, { kind: "arrivedAtStop" }, ALL);
      expect(state.mode).toBe("learn");
      expect(at(state)).toBe("lesson");
    }
  });

  test("opening a section overview is a request to read", () => {
    for (const from of STATES) {
      expect(at(reduceTabs(from, { kind: "openedSection" }, ALL))).toBe("lesson");
    }
  });

  test("expanding the map goes to the map, in route mode", () => {
    for (const from of STATES) {
      const state = reduceTabs(from, { kind: "expandedMap" }, ALL);
      expect(state.mode).toBe("route");
      expect(at(state)).toBe("map");
    }
  });

  test("Escape leaves route mode and is inert everywhere else", () => {
    // Otherwise Escape becomes a way to lose your place while answering.
    for (const from of STATES) {
      const state = reduceTabs(from, { kind: "dismissedRoute" }, ALL);
      if (from.mode === "route") {
        expect(state.mode).toBe("learn");
        // Back to whichever learn tab was open: leaving the map is going back.
        expect(at(state)).toBe(from.learn);
      } else {
        expect(state).toEqual(from);
      }
    }
  });

  test("Escape works from Analysis too, not only from the map", () => {
    // Both tabs are the same excursion from reading, and a key that worked on one
    // and silently failed on the other would read as a key that sometimes fails.
    const state = reduceTabs(INITIAL_TABS, { kind: "picked", tab: "analysis" }, ALL);
    expect(reduceTabs(state, { kind: "dismissedRoute" }, ALL).mode).toBe("learn");
  });
});

describe("the reducer is total and never lands nowhere", () => {
  test("every state times every event yields a tab this build renders", () => {
    for (const available of [ALL, NO_UNDERSTANDING, NEXT]) {
      for (const from of STATES) {
        for (const event of EVENTS) {
          const next = reduceTabs(from, event, available);
          expect(available, `${JSON.stringify(from)} + ${JSON.stringify(event)}`).toContain(
            activeTab(next, available)
          );
        }
      }
    }
  });

  test("the rendered tab always belongs to the rendered mode", () => {
    // The pairing the column branches on: it draws the learn column or the route
    // column from the mode, and the view inside it from the tab. A state where the
    // two disagree would render one mode's chrome around the other's view.
    for (const available of [ALL, NO_UNDERSTANDING, NEXT]) {
      for (const from of STATES) {
        for (const event of EVENTS) {
          const next = reduceTabs(from, event, available);
          if (modesIn(available).includes(next.mode)) {
            expect(modeOf(activeTab(next, available))).toBe(next.mode);
          }
        }
      }
    }
  });
});

describe("tabs and surfaces are not the same thing", () => {
  test("route mode's tabs are not surfaces", () => {
    expect(surfaceForTab("map")).toBeNull();
    expect(surfaceForTab("analysis")).toBeNull();
  });

  test("learn mode's are, and name themselves", () => {
    expect(surfaceForTab("lesson")).toBe("lesson");
    expect(surfaceForTab("understanding")).toBe("understanding");
  });
});

describe("a chapter overview has no Understanding to offer", () => {
  /**
   * Understanding is what the learner has SHOWN — a question, an answer, a verdict,
   * open gaps — and every one of those belongs to a stop. A chapter overview has no
   * question and nothing is demonstrated at chapter granularity, so the tab could
   * only open onto the previous stop's evidence beside a heading about something
   * else. Route mode is untouched: the journey and the evidence over it are the same
   * whichever chapter heading is open in the other mode.
   */
  test("learn mode is Lesson alone while an overview is open", () => {
    expect(tabsFor("surfaces", { sectionOverview: true })).toEqual([
      "lesson",
      "map",
      "analysis",
    ]);
  });

  test("and both again once it is closed", () => {
    expect(tabsFor("surfaces", { sectionOverview: false })).toEqual([
      "lesson",
      "understanding",
      "map",
      "analysis",
    ]);
    // Omitting the option means no overview — the common case stays the default.
    expect(tabsFor("surfaces")).toEqual(["lesson", "understanding", "map", "analysis"]);
  });

  test("the comparison build is untouched by it — it has no Understanding to drop", () => {
    expect(tabsFor("next", { sectionOverview: true })).toEqual(["lesson", "map"]);
    expect(tabsFor("next")).toEqual(["lesson", "map"]);
  });

  test("a stale pick of a tab that is no longer offered is ignored, not obeyed", () => {
    // The reducer already refuses tabs outside `available`; this is that guarantee
    // restated for the case where the list shrank rather than never having had it.
    const available = tabsFor("surfaces", { sectionOverview: true });
    const state = reduceTabs(INITIAL_TABS, { kind: "picked", tab: "understanding" }, available);
    expect(activeTab(state, available)).toBe("lesson");
  });

  test("a remembered Understanding falls back to Lesson while the overview is open", () => {
    // The state is not corrected — an effect that corrected it would be a second
    // thing that moves the selection — so the clamp is in `activeTab`, and the
    // remembered tab comes back when the overview closes.
    const state = reduceTabs(INITIAL_TABS, { kind: "picked", tab: "understanding" }, ALL);
    expect(activeTab(state, NO_UNDERSTANDING)).toBe("lesson");
    expect(activeTab(state, ALL)).toBe("understanding");
  });

  test("opening a section sends the learner to Lesson", () => {
    const state = reduceTabs(INITIAL_TABS, { kind: "picked", tab: "understanding" }, ALL);
    expect(activeTab(reduceTabs(state, { kind: "openedSection" }, ALL), ALL)).toBe("lesson");
  });
});
