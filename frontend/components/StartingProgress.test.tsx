import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { t } from "@/lib/strings";

/**
 * The generation screen, and the honesty rules it is easiest to break by accident.
 *
 * Everything on this screen except the goal is streamed by the backend, and the
 * rule the milestone states twice is that nothing may be invented: no percentage of
 * unknown work, no stage the server did not name, no elapsed time the tab's throttled
 * timer made up. So the tests are mostly about provenance — where each number came
 * from — rather than about layout.
 */

const api = vi.hoisted(() => ({ sessionProgress: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ...api,
}));

const STAGES = ["clone", "structure", "survey", "documentation", "investigation", "plan"];

const snapshot = (over: Record<string, unknown> = {}) => ({
  stages: STAGES,
  stage: "investigation",
  done: ["clone", "structure", "survey", "documentation"],
  activity: { tool: "read_file", target: "src/requests/sessions.py" },
  turn: 3,
  calls: 11,
  seconds: 42,
  finished: false,
  ...over,
});

async function renderScreen(goal?: Record<string, string> | null) {
  const { default: StartingProgress } = await import("@/components/StartingProgress");
  render(<StartingProgress repoUrl="https://github.com/psf/requests" progressId="run-1" goal={goal} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.sessionProgress.mockResolvedValue(snapshot());
});

afterEach(() => vi.useRealTimers());

describe("stage rows come from the server", () => {
  test("every stage the snapshot names is rendered, and the done ones are marked", async () => {
    await renderScreen();
    for (const key of STAGES) {
      expect(await screen.findByText(t.starting.stages[key])).toBeTruthy();
    }
    // Four of six done — asserted through the bar's width rather than a
    // percentage of unknown work, which is the rule this screen exists under.
    const bar = document.querySelector<HTMLElement>("[style*='width']");
    expect(bar!.style.width).toBe(`${(4 / 6) * 100}%`);
  });

  test("a stage the server does not name is not invented", async () => {
    api.sessionProgress.mockResolvedValue(snapshot({ stages: ["clone", "plan"], done: ["clone"] }));
    await renderScreen();
    await screen.findByText(t.starting.stages.clone);
    expect(screen.queryByText(t.starting.stages.survey)).toBeNull();
  });
});

describe("the activity is the real target", () => {
  test("rendered through the tool's own phrasing", async () => {
    await renderScreen();
    expect(
      await screen.findByText(t.starting.activity.read_file("src/requests/sessions.py"))
    ).toBeTruthy();
  });

  test("an unknown tool reads as unfamiliar rather than as nothing happening", async () => {
    api.sessionProgress.mockResolvedValue(
      snapshot({ activity: { tool: "some_new_primitive", target: "x.py" } })
    );
    await renderScreen();
    expect(await screen.findByText(t.starting.activityUnknown("x.py"))).toBeTruthy();
  });
});

describe("the accumulating file list (P3)", () => {
  test("files read are collected across polls, not shown once and discarded", async () => {
    api.sessionProgress
      .mockResolvedValueOnce(snapshot({ activity: { tool: "read_file", target: "a.py" } }))
      .mockResolvedValue(snapshot({ activity: { tool: "read_file", target: "b.py" } }));
    await renderScreen();

    await waitFor(() => expect(screen.getByText(t.starting.filesRead(2))).toBeTruthy());
    expect(screen.getByText("a.py")).toBeTruthy();
    expect(screen.getByText("b.py")).toBeTruthy();
  });

  test("the same file read twice is listed once", async () => {
    api.sessionProgress.mockResolvedValue(
      snapshot({ activity: { tool: "read_file", target: "same.py" } })
    );
    await renderScreen();
    await waitFor(() => expect(screen.getByText(t.starting.filesRead(1))).toBeTruthy());
    expect(screen.getAllByText("same.py")).toHaveLength(1);
  });

  test("only `read_file` counts — a search pattern is not a file", async () => {
    // The list is checkable against the learner's own checkout, and it stops being
    // checkable the moment a regex appears in it.
    api.sessionProgress.mockResolvedValue(
      snapshot({ activity: { tool: "search_code", target: "def prepare_auth" } })
    );
    await renderScreen();
    await screen.findByText(t.starting.activity.search_code("def prepare_auth"));
    expect(screen.queryByText(t.starting.filesRead(1))).toBeNull();
  });
});

describe("elapsed time is the server's, not the tab's", () => {
  test("the snapshot's seconds win over the local tick", async () => {
    // Browsers throttle timers in a hidden tab; this wait is long enough that
    // people look away. Measured drifting to 8s against a real 118s.
    await renderScreen();
    expect(await screen.findByText(t.starting.elapsed(42))).toBeTruthy();
  });

  test("past five minutes the copy stops promising two to four", async () => {
    api.sessionProgress.mockResolvedValue(snapshot({ seconds: 431 }));
    await renderScreen();
    const line = await screen.findByText(t.starting.elapsedLong(431));
    expect(line.textContent).toContain("taking longer than usual");
    expect(screen.queryByText(t.starting.elapsed(431))).toBeNull();
  });

  test("just under the threshold still promises it", async () => {
    api.sessionProgress.mockResolvedValue(snapshot({ seconds: 299 }));
    await renderScreen();
    expect(await screen.findByText(t.starting.elapsed(299))).toBeTruthy();
  });
});

describe("continuity with the interview (P3)", () => {
  test("the confirmed goal stays on screen through the wait", async () => {
    await renderScreen({ primary_goal: "Trace the request lifecycle end to end" });
    expect(await screen.findByText("Trace the request lifecycle end to end")).toBeTruthy();
    expect(screen.getByText(t.starting.goalHeading)).toBeTruthy();
  });

  test("no goal, no empty heading", async () => {
    await renderScreen(null);
    await screen.findByText(t.starting.stages.clone);
    expect(screen.queryByText(t.starting.goalHeading)).toBeNull();
  });
});
