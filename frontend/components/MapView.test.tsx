import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import MapView from "@/components/MapView";
import { node, seq } from "@/test/factories";
import { t } from "@/lib/strings";

/**
 * The map is the route, and only the route.
 *
 * It used to be the route plus the two progress measures, three outcome bands, the
 * pattern layer, two breakdown panels and a session-log column — all of which moved
 * to `AnalysisView` when route mode split into two tabs. The pattern-chip claims
 * moved with them, into `AnalysisView.test.tsx`.
 *
 * What is asserted here is the boundary from this side: the stops are navigable, and
 * the dashboard is gone. Re-merging is the easy accident — one measure added "for
 * context" and the map is a dashboard again — so it is a test rather than a comment.
 *
 * "Navigable" now means through the stop card. The claims about what the card SAYS
 * live in `StopCard.test.tsx`; what is here is only that the map opens one and that
 * the card is the single way out of the map into a lesson.
 */

const NODES = [node("n1", { title: "The adapter contract" }), node("n2", { title: "Pool keys" })];

// `null` rather than `undefined` for the no-handler case: a default parameter
// cannot tell "omitted" from "passed as undefined", and the recap depends on the
// difference.
function view(onGoToLesson: ((n: unknown) => void) | null = vi.fn()) {
  return {
    onGoToLesson,
    ...render(
      <MapView
        nodes={NODES}
        edges={[seq("n1", "n2")]}
        currentNodeId="n1"
        repoUrl="https://github.com/psf/requests"
        onGoToLesson={onGoToLesson ?? undefined}
      />
    ),
  };
}

/** The stop row in the route list, as distinct from the same title inside the card. */
const row = (title: string) =>
  screen.getAllByText(title).map((el) => el.closest("button")).find(Boolean)!;

/**
 * Text on the ROUTE, as opposed to the same words inside the key.
 *
 * The key speaks the map's vocabulary on purpose — that is what makes it a key —
 * so every assertion about what the route says has to say which of the two it
 * means. Addressed by the tour attribute rather than by a role, because that
 * attribute is a contract the tour already depends on.
 */
const onRoute = (text: string) => {
  const legend = document.querySelector('[data-tour="map-legend"]')?.closest("details");
  return screen.queryAllByText(text).filter((el) => !legend?.contains(el));
};

describe("the route", () => {
  test("every stop is on it, under the journey heading", () => {
    view();
    expect(screen.getByText(t.map.journeyTitle)).toBeTruthy();
    expect(screen.getByText("The adapter contract")).toBeTruthy();
    expect(screen.getByText("Pool keys")).toBeTruthy();
  });

  test("the repository is named, without the host and the .git", () => {
    view();
    expect(screen.getByText("psf/requests")).toBeTruthy();
  });
});

describe("a stop opens before it moves you", () => {
  test("clicking a stop opens its card and jumps nowhere", () => {
    const { onGoToLesson } = view();
    fireEvent.click(row("Pool keys"));

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(onGoToLesson).not.toHaveBeenCalled();
  });

  test("the card is the way to the lesson", () => {
    const { onGoToLesson } = view();
    fireEvent.click(row("Pool keys"));
    fireEvent.click(screen.getByRole("button", { name: t.map.stop.goToLesson }));

    expect(onGoToLesson).toHaveBeenCalledWith(expect.objectContaining({ id: "n2" }));
    // And it leaves, rather than sitting over the lesson it sent you to.
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("the stop you are standing on offers the way back, not a jump", () => {
    view();
    fireEvent.click(row("The adapter contract"));
    expect(screen.getByRole("button", { name: t.map.stop.returnToLesson })).toBeTruthy();
  });

  test("closing leaves you exactly where you were", () => {
    const { onGoToLesson } = view();
    fireEvent.click(row("Pool keys"));
    fireEvent.click(screen.getByRole("button", { name: t.map.stop.close }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(onGoToLesson).not.toHaveBeenCalled();
  });

  test("Escape closes it too", () => {
    view();
    fireEvent.click(row("Pool keys"));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  // The completion recap renders this same component with no handler. The card is
  // still worth reading there; the walk is over, so there is nowhere to walk to.
  test("with no handler the card describes the stop and offers no jump", () => {
    view(null);
    fireEvent.click(row("Pool keys"));

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.queryByRole("button", { name: t.map.stop.goToLesson })).toBeNull();
    expect(screen.queryByRole("button", { name: t.map.stop.returnToLesson })).toBeNull();
  });
});

describe("the analysis is not here", () => {
  test("no measures", () => {
    view();
    expect(onRoute(t.map.demonstratedLabel)).toHaveLength(0);
    expect(screen.queryByText(t.map.moreBreakdowns)).toBeNull();
  });

  test("no session log", () => {
    view();
    expect(screen.queryByText(t.log.label)).toBeNull();
  });
});

/**
 * An `optional` unit is depth the learner did not ask for. It sits ON the
 * sequence chain — the planner emitted it, the sizer demoted it — so the map
 * drew it flush on the spine, unindented and uncaptioned, while the rail filed
 * it under its collapsed "optional stops" group. Same graph, two answers, and
 * the surface a learner reads as "the journey" was the one claiming a planned
 * unit was an ordinary stop on it.
 */
describe("an optional stop is not on the promised walk", () => {
  const OPTIONAL = [
    node("n1", { title: "The adapter contract" }),
    node("n2", { title: "Pool keys", priority: "optional" }),
    node("n3", { title: "Retry budgets" }),
  ];

  const renderOptional = () =>
    render(
      <MapView
        nodes={OPTIONAL}
        edges={[seq("n1", "n2"), seq("n2", "n3")]}
        currentNodeId="n1"
        onGoToLesson={vi.fn()}
      />
    );

  test("it is captioned as off the walk, in the route itself", () => {
    renderOptional();
    expect(screen.getByText(t.map.stop.optional)).toBeTruthy();
  });

  test("and indented, so it does not read as a station", () => {
    renderOptional();
    expect(row("Pool keys").closest("li")!.className).toContain("ms-10");
    expect(row("Retry budgets").closest("li")!.className).not.toContain("ms-10");
  });

  // The caption is the *reason*, and it must not borrow the warm-up's. Nothing
  // happened here; this stop was simply never promised.
  test("it is not captioned as inserted after a wrong answer", () => {
    renderOptional();
    expect(onRoute(t.rail.addedAfterConfusion)).toHaveLength(0);
  });
});

/**
 * ── The route reads as a route ────────────────────────────────────────────────
 *
 * Everything asserted below is a DISTINCTION THE GRAPH ALREADY CARRIED and the
 * map was throwing away: the planner's chapters, which stop the learner is on,
 * what is still outstanding on a stop, and which stops left the trunk. None of
 * it is a new fact, which is why each test names the field it comes from.
 */

const AREAS = [
  { id: "contract", title: "Problem contract", why: "What is promised.", order: 1 },
  { id: "search", title: "Search and node", why: "How it is found.", order: 2 },
];

const CHAPTERED = [
  node("n1", { title: "Entry points", area_id: "contract", visited: true,
               understanding: "strength", attempted: true }),
  node("n2", { title: "The Response", area_id: "contract", visited: true }),
  node("n3", { title: "The Session object", area_id: "search",
               objective: "Say what a Session owns that a bare call does not." }),
  node("n4", { title: "Pool keys", area_id: "search", attempted: true,
               understanding: "unresolved",
               gaps: [{ id: "g1", kind: "wrong_model", claim: "a key is the host",
                        blocking: true, status: "open" }] }),
];

const CHAPTERED_EDGES = [seq("n1", "n2"), seq("n2", "n3"), seq("n3", "n4")];

const chaptered = (currentNodeId = "n3") =>
  render(
    <MapView
      nodes={CHAPTERED}
      edges={CHAPTERED_EDGES}
      areas={AREAS}
      currentNodeId={currentNodeId}
      repoUrl="https://github.com/psf/requests"
      onGoToLesson={vi.fn()}
    />
  );

describe("chapters come from the planner's areas", () => {
  test("each area heads its own run, numbered in walk order", () => {
    chaptered();
    expect(screen.getByText("Problem contract")).toBeTruthy();
    expect(screen.getByText("Search and node")).toBeTruthy();
    expect(screen.getByText("01")).toBeTruthy();
    expect(screen.getByText("02")).toBeTruthy();
  });

  // Counted by `buildSections`, which counts stations the way `progress.py`
  // does — so a chapter's counter cannot disagree with the rail's.
  test("a chapter counts the stops behind you within it", () => {
    chaptered();
    expect(screen.getByText(t.rail.sectionProgress(2, 2))).toBeTruthy();
    expect(screen.getByText(t.rail.sectionProgress(0, 2))).toBeTruthy();
  });

  // A pre-B3 graph has no areas. It rendered as one plain run before chapters
  // existed and must still do so, rather than growing an invented heading.
  test("a graph with no areas grows no headings", () => {
    view();
    expect(screen.queryByText("01")).toBeNull();
  });
});

describe("where you are standing", () => {
  test("the current stop says so in words, not only in cyan", () => {
    chaptered();
    expect(onRoute(t.rail.youAreHere)).toHaveLength(1);
  });

  test("and it is the only stop that shows its objective", () => {
    chaptered();
    const objective = "Say what a Session owns that a bare call does not.";
    expect(screen.getByText(objective)).toBeTruthy();
    expect(screen.getAllByText(objective)).toHaveLength(1);
  });

  test("with no current node nothing claims to be here", () => {
    chaptered("");
    expect(onRoute(t.rail.youAreHere)).toHaveLength(0);
  });
});

/**
 * ONE status line per stop, in the rail's own words. The map used to print the
 * understanding class alone, so a stop the learner walked past and one nobody
 * had opened were captioned identically — with nothing.
 */
describe("what is still true of a stop", () => {
  test("open misconceptions outrank everything else", () => {
    chaptered();
    expect(screen.getByText(t.rail.unresolvedCount(1))).toBeTruthy();
  });

  test("a stop reached and walked past says so", () => {
    chaptered();
    expect(screen.getByText(t.rail.passedBy)).toBeTruthy();
  });

  test("a demonstrated stop is named by its understanding class", () => {
    chaptered();
    expect(onRoute(t.map.understanding.strength)).toHaveLength(1);
  });
});

/**
 * The one line of context the map adds. Every number is counted off the stops on
 * screen with the definitions the backend uses, and none of them repeats a
 * measure the session header already reports.
 */
describe("the route's own shape", () => {
  test("stops walked, chapters, and what is outstanding", () => {
    chaptered();
    expect(screen.getByText(t.map.stopsTaken(2, 4))).toBeTruthy();
    expect(screen.getByText(t.map.chapterCount(2))).toBeTruthy();
    expect(screen.getByText(t.map.needWork(1))).toBeTruthy();
  });

  // "needs work" is an OPEN task — unresolved understanding that the learner has
  // not closed. A journey with none of those must not display a zero.
  test("nothing outstanding says nothing at all", () => {
    view();
    expect(screen.queryByText(t.map.needWork(0))).toBeNull();
  });
});

/**
 * ── The key ───────────────────────────────────────────────────────────────────
 *
 * A visual language nobody is taught is decoration. What is asserted here is that
 * the key covers what a learner can actually meet on the route — including the
 * branches, which are the part that changes under them — that it costs nothing
 * while closed, and that it is a `<details>`, which is where its keyboard
 * behaviour comes from.
 */
describe("the key", () => {
  const legend = () => document.querySelector('[data-tour="map-legend"]')!.closest("details")!;

  test("is closed on arrival and opens from its own control", () => {
    chaptered();
    expect((legend() as HTMLDetailsElement).open).toBe(false);
    // A `<summary>` is keyboard-operable as itself — Enter and Space toggle the
    // `<details>` with no handler of ours, which is the reason it is one.
    const summary = legend().querySelector("summary")!;
    expect(summary.tagName).toBe("SUMMARY");
    expect(screen.getByText(t.map.legend.open)).toBeTruthy();
  });

  test("names every marker the route can draw", () => {
    chaptered();
    const key = within(legend() as HTMLElement);
    expect(key.getByText(t.rail.youAreHere)).toBeTruthy();
    expect(key.getByText(t.map.understanding.strength)).toBeTruthy();
    expect(key.getByText(t.map.understanding.recovered)).toBeTruthy();
    expect(key.getByText(t.map.understanding.unresolved)).toBeTruthy();
    expect(key.getByText(t.map.understanding.insufficient)).toBeTruthy();
    expect(key.getByText(t.rail.attempted)).toBeTruthy();
    expect(key.getByText(t.map.legend.closedLabel)).toBeTruthy();
  });

  // The branches are the reason the key matters most: they are the only thing on
  // the map that means the journey changed because of what the learner did.
  test("and both kinds of branch, with the difference between them", () => {
    chaptered();
    const key = within(legend() as HTMLElement);
    expect(key.getByText(t.rail.addedAfterConfusion)).toBeTruthy();
    expect(key.getByText(t.map.legend.branchWarmUp)).toBeTruthy();
    expect(key.getByText(t.map.legend.optionalLabel)).toBeTruthy();
    expect(key.getByText(t.map.legend.branchOptional)).toBeTruthy();
  });

  test("and both halves of the line", () => {
    chaptered();
    const key = within(legend() as HTMLElement);
    expect(key.getByText(t.map.legend.walkedLabel)).toBeTruthy();
    expect(key.getByText(t.map.legend.aheadLabel)).toBeTruthy();
  });

  /**
   * The pins in the key are the REAL component, driven by the same server-sent
   * facts the route passes it, so the key cannot drift from what it explains.
   * Seven rows, seven pins — the count is what would break first if a row were
   * ever replaced by a hand-drawn circle.
   */
  test("draws the markers rather than describing them", () => {
    chaptered();
    // The marker cell's own child, not every circle in the tree: the current
    // pin carries an inner dot that is a `rounded-full` of its own.
    const drawn = legend().querySelectorAll("li > span > span.rounded-full");
    expect(drawn.length).toBe(7);
  });
});
