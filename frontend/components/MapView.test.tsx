import { fireEvent, render, screen } from "@testing-library/react";
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
    expect(screen.queryByText(t.map.demonstratedLabel)).toBeNull();
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
    expect(screen.queryByText(t.rail.addedAfterConfusion)).toBeNull();
  });
});
