import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import RebuildingOverlay from "@/components/RebuildingOverlay";
import { t } from "@/lib/strings";

/**
 * The restart's wait.
 *
 * What is load-bearing here is that the wait is VISIBLE and that a failure is
 * REPORTED. Before this surface existed, `Start over` disabled a menu item and
 * then re-ran the entire pipeline in silence for two to four minutes — and a run
 * that failed reset the item and said nothing, so success-in-progress and
 * outright failure looked identical from the outside.
 */

// The progress poll is `StartingProgress`'s own concern and is covered where it
// lives. Stubbed here so this file tests the restart's framing, not the stream —
// and spread over the real module so everything else the tree imports is intact.
const api = vi.hoisted(() => ({ sessionProgress: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  ...api,
}));

const SNAPSHOT = {
  stages: ["clone", "plan"],
  stage: "clone",
  done: [],
  activity: null,
  turn: 0,
  calls: 0,
  seconds: 3,
  finished: false,
};

const props = () => ({
  repoUrl: "https://github.com/psf/requests",
  goal: { primary_goal: "understand the request lifecycle" },
  progressId: "run-1",
  error: null as string | null,
  onRetry: vi.fn(),
  onDismiss: vi.fn(),
});

let p: ReturnType<typeof props>;

beforeEach(() => {
  vi.clearAllMocks();
  api.sessionProgress.mockResolvedValue(SNAPSHOT);
  p = props();
});

describe("while the restart is running", () => {
  test("says the pipeline is running, and what it is running on", async () => {
    render(<RebuildingOverlay {...p} />);

    expect(await screen.findByText(t.session.rebuildWaitLabel)).toBeTruthy();
    expect(screen.getByText("psf/requests")).toBeTruthy();
    // The stage checklist is on screen, so the wait is never a blank box.
    expect(screen.getByText(t.starting.stages.clone)).toBeTruthy();
  });

  test("keeps the goal on screen, so the wait says what it is for", async () => {
    render(<RebuildingOverlay {...p} />);
    expect(await screen.findByText("understand the request lifecycle")).toBeTruthy();
  });

  test("says what happens to the session being replaced", async () => {
    render(<RebuildingOverlay {...p} />);
    expect(await screen.findByText(t.session.rebuildWaitNote)).toBeTruthy();
  });

  test("offers a way out that does not claim to cancel the run", async () => {
    render(<RebuildingOverlay {...p} />);
    await screen.findByText(t.session.rebuildWaitNote);

    await userEvent.click(
      screen.getByRole("button", { name: t.session.rebuildWaitCancel })
    );

    expect(p.onDismiss).toHaveBeenCalledTimes(1);
    expect(p.onRetry).not.toHaveBeenCalled();
  });
});

describe("when the restart fails", () => {
  const failed = { error: "no_graph\ncould not plan a route" };

  test("names the failure and shows what the server said", () => {
    render(<RebuildingOverlay {...p} {...failed} />);

    expect(screen.getByText(t.session.rebuildWaitFailed)).toBeTruthy();
    expect(screen.getByText(/could not plan a route/)).toBeTruthy();
  });

  test("says the session they were in is still there", () => {
    render(<RebuildingOverlay {...p} {...failed} />);
    expect(screen.getByText(t.session.rebuildWaitReassurance)).toBeTruthy();
  });

  test("the wait is gone — a failed run must not look like a running one", () => {
    render(<RebuildingOverlay {...p} {...failed} />);
    expect(screen.queryByText(t.starting.stages.clone)).toBeNull();
  });

  test("both ways out are offered, and they are different actions", async () => {
    render(<RebuildingOverlay {...p} {...failed} />);

    await userEvent.click(screen.getByRole("button", { name: t.session.rebuildWaitRetry }));
    expect(p.onRetry).toHaveBeenCalledTimes(1);
    expect(p.onDismiss).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: t.session.rebuildWaitCancel }));
    expect(p.onDismiss).toHaveBeenCalledTimes(1);
  });
});
