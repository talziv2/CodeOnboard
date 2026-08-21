import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import AnalysisView from "@/components/AnalysisView";
import { node, seq } from "@/test/factories";
import { t } from "@/lib/strings";
import type {
  Pattern, Progress, SessionGraph, UnderstandingProfile,
} from "@/lib/api";

/**
 * One claim, found from a live console rather than from reading the code: a
 * pattern's evidence chips must all render.
 *
 * `node_id` + `attempt_index` looks unique and is not. A pattern groups by kind,
 * and a single answer can contain two gaps of the same kind on the same unit, so
 * the backend legitimately sends two refs with both fields equal and React saw two
 * children under one key. Found in a live console, not by reading the code.
 *
 * What it did NOT do is drop a chip — verified by putting the duplicate key back,
 * which fails only the warning test below. Duplicate keys are documented as
 * unsupported ("may cause children to be duplicated and/or omitted"), so the bug
 * is relying on a guarantee we did not hold; the count beside the chips comes from
 * `evidence.length`, and a dropped chip would mean the row says "2 answers behind
 * this" over one openable chip. Both claims are asserted separately for that
 * reason: the visible one, and the warning that says we were owed it by luck.
 *
 * This suite was `MapView.test.tsx` until the map and the analysis of it became two
 * tabs of route mode. The patterns moved; the claim did not.
 */

const NODES = [node("n1", { title: "The adapter contract" }), node("n2", { title: "Pool keys" })];

/** Two refs, same unit, same attempt — what the duplicate key collided on. */
const PATTERN: Pattern = {
  template: "gap_outcomes",
  detail: { opened: 2, closed: 0 },
  evidence: [
    { node_id: "n1", attempt_index: 0 },
    { node_id: "n1", attempt_index: 0 },
  ],
};

const PROFILE: UnderstandingProfile = {
  patterns: [],
  gap_patterns: [PATTERN],
  totals: { understood: 0, partial: 1, failed: 0, not_started: 1 },
  assessed: 1,
  total: 2,
  by_area: {},
  by_kind: {},
  needs_work: [],
  set_aside: [],
  recovered: [],
  nodes: [],
} as unknown as UnderstandingProfile;

/** Complete rather than cast-and-hope: the view reads most of these. */
const PROGRESS: Progress = {
  goal_readiness: 0.5,
  core_total: 2,
  core_demonstrated: 1,
  core_in_progress: 0,
  core_unassessed: 1,
  journey_progress: 0.5,
  stops_settled: 1,
  stops_total: 2,
  assessed_coverage: 0.5,
  assessed: 1,
  detours: [],
  skipped: 0,
  optional_total: 0,
  optional_completed: 0,
};

/** The view takes the session graph, so the fixture is one. */
const GRAPH = {
  session_id: "s1",
  repo_url: "https://github.com/psf/requests",
  goal: {},
  current_node_id: "n1",
  nodes: NODES,
  edges: [seq("n1", "n2")],
  readiness: 0.5,
  progress: PROGRESS,
  understanding: PROFILE,
} as unknown as SessionGraph;

function view(onOpenEvidence = vi.fn()) {
  return { onOpenEvidence, ...render(<AnalysisView graph={GRAPH} onOpenEvidence={onOpenEvidence} />) };
}

let errors: unknown[][];

beforeEach(() => {
  errors = [];
  vi.spyOn(console, "error").mockImplementation((...args) => {
    errors.push(args);
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("every piece of evidence a pattern claims is reachable", () => {
  test("two refs on the same unit and attempt render two chips", () => {
    view();
    // Labelled `1 of 2` / `2 of 2` — a bare "1" is the whole accessible name
    // otherwise, which is why the label carries the position.
    expect(screen.getByRole("button", { name: t.map.evidenceRef(1, 2) })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.map.evidenceRef(2, 2) })).toBeTruthy();
  });

  test("the count beside the chips matches how many there are", () => {
    view();
    expect(screen.getByText(t.map.patternEvidence(2))).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /^Open the evidence for answer/ })).toHaveLength(2);
  });

  test("no duplicate-key warning — the keys are actually distinct", () => {
    view();
    const duplicate = errors.filter((args) =>
      args.some((a) => typeof a === "string" && a.includes("same key"))
    );
    expect(duplicate).toEqual([]);
  });

  test("each chip opens the unit its ref names", () => {
    const { onOpenEvidence } = view();
    screen.getAllByRole("button", { name: /^Open the evidence for answer/ })[1].click();
    expect(onOpenEvidence).toHaveBeenCalledWith("n1");
  });
});

describe("the split left each tab with its own half", () => {
  /**
   * The two views are one mode and easy to re-merge by accident — a measure added
   * "for context" on the map, a route list added "for reference" here. These two
   * assertions are the boundary: the numbers are here, and the stops are not.
   */
  test("the measures are in Analysis", () => {
    view();
    expect(screen.getByText(t.map.demonstratedLabel)).toBeTruthy();
    expect(
      screen.getByText(t.map.assessedOf(PROFILE.assessed, PROFILE.total))
    ).toBeTruthy();
  });

  test("the route is not — it belongs to the map", () => {
    view();
    expect(screen.queryByText("The adapter contract")).toBeNull();
    expect(screen.queryByText(t.map.journeyTitle)).toBeNull();
  });

  test("what the system did is here, where the rest of the account is", () => {
    view();
    expect(screen.getByText(t.log.label)).toBeTruthy();
  });
});
