import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import StopCard from "@/components/StopCard";
import { buildRoute } from "@/lib/graph-layout";
import { node, prereq, seq } from "@/test/factories";
import { t } from "@/lib/strings";

/**
 * What the card is allowed to say.
 *
 * The rule it exists under: **every line is a reading of the graph.** The card
 * fetches nothing and generates nothing, so the failure it must not have is
 * inventing — an objective where the graph has none, a state where there is no
 * evidence, a position for a stop the counter does not count. Each of those is
 * asserted below, because each is a sentence a reader would believe.
 */

function card(
  nodes = [node("n1"), node("n2")],
  edges = [seq("n1", "n2")],
  id = "n2",
  over: Partial<React.ComponentProps<typeof StopCard>> = {}
) {
  const stops = buildRoute(nodes, edges);
  const stop = stops.find((s) => s.node.id === id)!;
  const onGoToLesson = vi.fn();
  const onClose = vi.fn();
  return {
    onGoToLesson,
    onClose,
    ...render(
      <StopCard
        stop={stop}
        spineLength={stops.filter((s) => !s.isPrerequisite).length}
        isCurrent={false}
        onGoToLesson={onGoToLesson}
        onClose={onClose}
        {...over}
      />
    ),
  };
}

describe("what the stop is", () => {
  test("the objective is the Planner's own words", () => {
    card([node("n1"), node("n2", { objective: "Explain what a pool key identifies" })]);
    expect(screen.getByText("Explain what a pool key identifies")).toBeTruthy();
  });

  test("a stop with no objective says so rather than showing an empty space", () => {
    card();
    expect(screen.getByText(t.map.stop.noObjective)).toBeTruthy();
  });

  test("its place on the route is the number the rail would give it", () => {
    card();
    expect(screen.getByText(t.lesson.stopOf(2, 2))).toBeTruthy();
  });

  test("every concept tag, not the two the map row has room for", () => {
    card([node("n1"), node("n2", { concept_tags: ["flow", "risk", "retries"] })]);
    expect(screen.getByText(t.tags.flow)).toBeTruthy();
    expect(screen.getByText(t.tags.risk)).toBeTruthy();
    expect(screen.getByText("retries")).toBeTruthy();
  });

  test("the code it is grounded in, display anchor and the rest", () => {
    card([
      node("n1"),
      node("n2", {
        file: "requests/adapters.py",
        line_start: 40,
        line_end: 80,
        anchors: [
          { file: "requests/adapters.py", line_start: 40, line_end: 80, symbol: "send" },
          { file: "urllib3/poolmanager.py", line_start: 5, line_end: 30, symbol: "key" },
        ],
      }),
    ]);
    expect(screen.getByText(/requests\/adapters\.py/)).toBeTruthy();
    expect(screen.getByText(/urllib3\/poolmanager\.py/)).toBeTruthy();
  });
});

describe("what the evidence shows, and no more", () => {
  test("an untouched stop is untouched, not 'needs work'", () => {
    card();
    expect(screen.getByText(t.map.stop.untouched)).toBeTruthy();
    expect(screen.getByText(t.map.understanding.insufficient)).toBeTruthy();
  });

  test("open gaps are counted where there are any", () => {
    card([
      node("n1"),
      node("n2", {
        understanding: "unresolved",
        gaps: [
          { id: "g1", kind: "wrong_model", claim: "pools are per-request", blocking: true, status: "open" },
          { id: "g2", kind: "wrong_model", claim: "settled", blocking: false, status: "verified" },
        ],
      }),
    ]);
    expect(screen.getByText(t.lesson.briefGaps(1))).toBeTruthy();
    expect(screen.getByText(t.map.understanding.unresolved)).toBeTruthy();
  });
});

describe("stops that are not stations", () => {
  test("a warm-up is captioned as one and names what it unlocks", () => {
    // The Mutator's shape: the incoming sequence edge is rerouted onto the warm-up,
    // which is then joined to the stop it unblocks by a `prerequisite` edge.
    card(
      [node("n1"), node("w1", { title: "Warm-up" }), node("n2", { title: "Pool keys" })],
      [seq("n1", "w1"), prereq("w1", "n2")],
      "w1"
    );
    expect(screen.getByText(t.lesson.warmUpHeading)).toBeTruthy();
    expect(screen.getByText(t.map.unlocks("Pool keys"))).toBeTruthy();
  });

  test("an optional stop is named off the walk instead of being numbered", () => {
    card([node("n1"), node("n2", { priority: "optional" })]);
    expect(screen.getByText(t.map.stop.offRoute)).toBeTruthy();
    expect(screen.getByText(t.map.stop.optional)).toBeTruthy();
  });
});
