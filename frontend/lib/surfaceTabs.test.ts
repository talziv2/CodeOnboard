import { describe, expect, test } from "vitest";
import type { LessonPhase } from "@/lib/lessonPhase";
import {
  nextTab,
  surfaceForTab,
  tabsFor,
  type SessionTab,
  type TabEvent,
} from "@/lib/surfaceTabs";

/**
 * The tab model, and R5.
 *
 * R5 is the risk that the phase model starts driving navigation. The strongest
 * assertion available is not a test at all — `TabEvent` has no phase in it and
 * `nextTab` takes no phase, so a phase cannot reach the decision. What the tests add
 * is the rest: that every event does what it claims, that no event can land on a tab
 * this build does not render, and that the phase-free property is checked rather
 * than merely intended.
 */

const THREE: SessionTab[] = ["lesson", "understanding", "map"];
const TWO: SessionTab[] = ["lesson", "map"];

const EVENTS: TabEvent[] = [
  { kind: "picked", tab: "lesson" },
  { kind: "picked", tab: "understanding" },
  { kind: "picked", tab: "map" },
  { kind: "arrivedAtStop" },
  { kind: "openedSection" },
  { kind: "expandedMap" },
  { kind: "dismissedMap" },
];

describe("which tabs a build offers", () => {
  test("surfaces gets three, in bar order", () => {
    expect(tabsFor("surfaces")).toEqual(["lesson", "understanding", "map"]);
  });

  test("next keeps the two it had", () => {
    // `legacy` used to be asserted here too. The renderer is gone (L5), so the
    // value no longer exists to ask about.
    expect(tabsFor("next")).toEqual(["lesson", "map"]);
  });
});

describe("R5 · a phase can never move the tab", () => {
  test("no event in the union mentions a phase", () => {
    // The type already guarantees it. This asserts the shape a future edit would
    // have to break on purpose: an event carrying `phase`, `result` or `lesson`.
    for (const event of EVENTS) {
      expect(Object.keys(event).every((k) => k === "kind" || k === "tab")).toBe(true);
    }
  });

  test("the same event from the same tab is the same answer, whatever the phase", () => {
    // `nextTab` has no phase parameter, so this is a property of its signature.
    // Written out anyway, over all four phases, because the claim the design makes
    // is behavioural — "submitting an answer does not switch tabs" — and this is
    // the closest a pure test comes to it.
    const phases: LessonPhase[] = ["STUDY", "FEEDBACK", "VERIFY", "RESOLVED"];
    for (const from of THREE) {
      for (const event of EVENTS) {
        const answers = phases.map(() => nextTab(from, event, THREE));
        expect(new Set(answers).size, `${from} + ${event.kind}`).toBe(1);
      }
    }
  });

  test("with no event, the tab does not move", () => {
    // There is no "phase changed" event to fire, which is the point: the only way
    // to not move is to have nothing to call.
    for (const from of THREE) {
      expect(nextTab(from, { kind: "picked", tab: from }, THREE)).toBe(from);
    }
  });
});

describe("what each event does", () => {
  test("picking a tab selects it", () => {
    expect(nextTab("lesson", { kind: "picked", tab: "understanding" }, THREE)).toBe(
      "understanding"
    );
    expect(nextTab("map", { kind: "picked", tab: "lesson" }, THREE)).toBe("lesson");
  });

  test("picking a tab this build does not render changes nothing", () => {
    // Under `next` there is no Understanding. A stale event naming it must be
    // ignored rather than blanking the column.
    expect(nextTab("lesson", { kind: "picked", tab: "understanding" }, TWO)).toBe("lesson");
    expect(nextTab("map", { kind: "picked", tab: "understanding" }, TWO)).toBe("map");
  });

  test("arriving at a different stop returns to Lesson, from anywhere", () => {
    // Not a phase transition — the learner navigated. Landing on a new stop showing
    // the previous stop's Understanding, its verdict and gaps gone, would be showing
    // them an empty room.
    for (const from of THREE) {
      expect(nextTab(from, { kind: "arrivedAtStop" }, THREE)).toBe("lesson");
    }
  });

  test("opening a section overview is a request to read", () => {
    for (const from of THREE) {
      expect(nextTab(from, { kind: "openedSection" }, THREE)).toBe("lesson");
    }
  });

  test("expanding the map goes to the map", () => {
    for (const from of THREE) {
      expect(nextTab(from, { kind: "expandedMap" }, THREE)).toBe("map");
    }
  });

  test("Escape is scoped to the map and is inert everywhere else", () => {
    // Otherwise Escape becomes a way to lose your place while answering.
    expect(nextTab("map", { kind: "dismissedMap" }, THREE)).toBe("lesson");
    expect(nextTab("understanding", { kind: "dismissedMap" }, THREE)).toBe("understanding");
    expect(nextTab("lesson", { kind: "dismissedMap" }, THREE)).toBe("lesson");
  });
});

describe("the reducer is total and never lands nowhere", () => {
  test("every tab times every event yields a tab this build renders", () => {
    for (const available of [THREE, TWO]) {
      for (const from of available) {
        for (const event of EVENTS) {
          expect(available, `${from} + ${JSON.stringify(event)}`).toContain(
            nextTab(from, event, available)
          );
        }
      }
    }
  });
});

describe("tabs and surfaces are not the same thing", () => {
  test("the map is not a surface", () => {
    expect(surfaceForTab("map")).toBeNull();
  });

  test("the other two are, and name themselves", () => {
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
   * else. The overview renders inside the `tab !== "map"` branch, so before this it
   * drew under Understanding too and the bar was claiming a view that did not exist.
   */
  test("the bar is Lesson and Map while an overview is open", () => {
    expect(tabsFor("surfaces", { sectionOverview: true })).toEqual(["lesson", "map"]);
  });

  test("and all three again once it is closed", () => {
    expect(tabsFor("surfaces", { sectionOverview: false })).toEqual([
      "lesson",
      "understanding",
      "map",
    ]);
    // Omitting the option means no overview — the common case stays the default.
    expect(tabsFor("surfaces")).toEqual(["lesson", "understanding", "map"]);
  });

  test("the comparison build is untouched by it — it has no Understanding to drop", () => {
    expect(tabsFor("next", { sectionOverview: true })).toEqual(["lesson", "map"]);
    expect(tabsFor("next")).toEqual(["lesson", "map"]);
  });

  test("a stale pick of a tab that is no longer offered is ignored, not obeyed", () => {
    // The reducer already refuses tabs outside `available`; this is that guarantee
    // restated for the case where the list shrank rather than never having had it.
    const available = tabsFor("surfaces", { sectionOverview: true });
    expect(nextTab("lesson", { kind: "picked", tab: "understanding" }, available)).toBe(
      "lesson"
    );
  });

  test("opening a section sends the learner to Lesson", () => {
    expect(
      nextTab("understanding", { kind: "openedSection" }, tabsFor("surfaces"))
    ).toBe("lesson");
  });
});
