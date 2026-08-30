import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import type { SessionGraph } from "@/lib/api";
import { t } from "@/lib/strings";

/**
 * The way out of a session is navigation and nothing else.
 *
 * Every other control in this header changes the session — scope, start over,
 * rebuild, finish — and three of them are destructive. That is the whole reason
 * this one is asserted rather than assumed: the failure that matters is not "the
 * link is missing", it is "the link is there and it also did something". So the
 * test presses it and then asserts that every session-mutating callback the
 * header holds was never called, alongside the one thing it must do.
 */

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

import DashboardLink from "@/components/DashboardLink";
import SessionHeader from "@/components/SessionHeader";

const GRAPH = {
  session_id: "s1",
  repo_url: "https://github.com/psf/requests",
  goal: { primary_goal: "understand the request lifecycle", depth: "moderate" },
  current_node_id: "n1",
  has_plan: true,
  nodes: [],
  edges: [],
  readiness: 0.4,
  progress: {
    goal_readiness: 0.4,
    core_total: 5,
    core_demonstrated: 2,
    core_in_progress: 1,
    core_unassessed: 2,
    journey_progress: 0.4,
    stops_settled: 2,
    stops_total: 5,
    assessed_coverage: 0.4,
    assessed: 2,
    detours: [],
    skipped: 0,
    optional_total: 0,
    optional_completed: 0,
  },
  understanding: {
    patterns: [],
    gap_patterns: [],
    totals: { strength: 0, recovered: 0, unresolved: 0, insufficient: 0 },
    assessed: 0,
    total: 0,
    by_area: {},
    by_kind: {},
  },
} as unknown as SessionGraph;

/** Everything the header can do TO the session, so a press can be shown not to. */
const mutators = {
  onScope: vi.fn(),
  onStartOver: vi.fn(),
  onRebuild: vi.fn(),
  onFinish: vi.fn(),
};

function renderHeader() {
  return render(
    <SessionHeader
      graph={GRAPH}
      depth="moderate"
      pct={40}
      stopCount={5}
      scoping={false}
      scopeNote={null}
      onScope={mutators.onScope}
      onBriefing={vi.fn()}
      onReplayTour={vi.fn()}
      onStartOver={mutators.onStartOver}
      startingOver={false}
      canStartOver
      onRebuild={mutators.onRebuild}
      rebuilding={false}
      onFinish={mutators.onFinish}
    />
  );
}

beforeEach(() => {
  push.mockClear();
  Object.values(mutators).forEach((fn) => fn.mockClear());
});

describe("the way back to the dashboard", () => {
  test("is present in the session header", () => {
    renderHeader();
    expect(
      screen.getByRole("button", { name: t.dashboard.backToDashboard })
    ).toBeDefined();
  });

  test("navigates to the sessions list through the router", async () => {
    renderHeader();
    await userEvent.click(
      screen.getByRole("button", { name: t.dashboard.backToDashboard })
    );
    expect(push).toHaveBeenCalledWith("/sessions");
  });

  test("changes nothing about the session it leaves", async () => {
    renderHeader();
    await userEvent.click(
      screen.getByRole("button", { name: t.dashboard.backToDashboard })
    );
    Object.values(mutators).forEach((fn) => expect(fn).not.toHaveBeenCalled());
  });

  test("names the destination even when the label is collapsed", () => {
    render(<DashboardLink />);
    const control = screen.getByRole("button", {
      name: t.dashboard.backToDashboard,
    });
    // Below `sm` only the arrow is drawn, so the sentence has to live on the
    // control itself rather than in the text node that disappears.
    expect(control.getAttribute("title")).toBe(t.dashboard.backToDashboard);
    expect(control.textContent).toContain(t.dashboard.mySessions);
  });
});
