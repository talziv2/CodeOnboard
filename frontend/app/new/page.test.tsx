import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { t } from "@/lib/strings";

/**
 * The landing page.
 *
 * Two things here are load-bearing and easy to break by accident. The first is
 * that both failure paths stay legible: an unreachable repository and an
 * unreachable server are different sentences, and the interview must not start
 * on either. The second is the expectation line — it exists to describe the wait
 * before it happens, and the whole point is that it contains no invented number.
 * A future edit "tightening the copy" into "about two minutes" would be a
 * regression of the same kind as a fake progress percentage, so it is asserted
 * rather than trusted.
 */

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const api = vi.hoisted(() => ({
  checkRepo: vi.fn(),
  sessionStart: vi.fn(),
  getSessionSummary: vi.fn(),
  sessionProgress: vi.fn(),
  goalStart: vi.fn(),
  goalAnswer: vi.fn(),
  goalBack: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

// The landing flow moved to `/new` in M5 — `/` is now a redirect to the
// dashboard (or to login). This suite follows the flow, not the path.
import Home from "@/app/new/page";

const RECENT_KEY = "codeonboard:recent-repos";

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe("the repository step", () => {
  test("a recognised backend reason is shown as a sentence, and the interview does not start", async () => {
    api.checkRepo.mockResolvedValue({ ok: false, reason: "no_graph" });
    render(<Home />);

    await userEvent.type(screen.getByLabelText(t.home.repoLabel), "https://github.com/nope/nope");
    await userEvent.click(screen.getByRole("button", { name: t.home.start }));

    // Mapped through `errorText`, not printed as the raw slug.
    await waitFor(() => expect(screen.getByText(t.errors.no_graph)).toBeTruthy());
    expect(screen.queryByText("no_graph")).toBeNull();
    expect(screen.getByLabelText(t.home.repoLabel)).toBeTruthy();
  });

  test("an unrecognised reason is passed through rather than swallowed", async () => {
    // `errorText` deliberately passes anything it does not recognise straight
    // through: a real pipeline message is more use than a generic apology.
    api.checkRepo.mockResolvedValue({ ok: false, reason: "clone failed: exit 128" });
    render(<Home />);

    await userEvent.type(screen.getByLabelText(t.home.repoLabel), "https://github.com/nope/nope");
    await userEvent.click(screen.getByRole("button", { name: t.home.start }));

    await waitFor(() => expect(screen.getByText("clone failed: exit 128")).toBeTruthy());
  });

  test("no reason at all still says something", async () => {
    api.checkRepo.mockResolvedValue({ ok: false, reason: null });
    render(<Home />);

    await userEvent.type(screen.getByLabelText(t.home.repoLabel), "https://github.com/nope/nope");
    await userEvent.click(screen.getByRole("button", { name: t.home.start }));

    await waitFor(() => expect(screen.getByText(t.home.repoUnreachable)).toBeTruthy());
  });

  test("a dead backend reports the server, with how to fix it", async () => {
    api.checkRepo.mockRejectedValue(new Error("server_unreachable"));
    render(<Home />);

    await userEvent.type(screen.getByLabelText(t.home.repoLabel), "https://github.com/psf/requests");
    await userEvent.click(screen.getByRole("button", { name: t.home.start }));

    await waitFor(() => expect(screen.getByText(t.errors.server_unreachable)).toBeTruthy());
  });

  test("a recent repository populates the field", async () => {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(["https://github.com/psf/requests"]));
    render(<Home />);

    const chip = await screen.findByRole("button", { name: "psf/requests" });
    await userEvent.click(chip);

    expect((screen.getByLabelText(t.home.repoLabel) as HTMLInputElement).value).toBe(
      "https://github.com/psf/requests",
    );
  });

  test("choosing a recent repository clears a previous error", async () => {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(["https://github.com/psf/requests"]));
    api.checkRepo.mockResolvedValue({ ok: false, reason: null });
    render(<Home />);

    await userEvent.type(screen.getByLabelText(t.home.repoLabel), "https://github.com/nope/nope");
    await userEvent.click(screen.getByRole("button", { name: t.home.start }));
    await waitFor(() => expect(screen.getByText(t.home.repoUnreachable)).toBeTruthy());

    await userEvent.click(await screen.findByRole("button", { name: "psf/requests" }));
    expect(screen.queryByText(t.home.repoUnreachable)).toBeNull();
  });

  test("the recents row is absent for a first-time visitor", () => {
    render(<Home />);
    expect(screen.queryByText(t.home.recent)).toBeNull();
  });
});

describe("the expectation line", () => {
  test("is shown before the wait, on the landing itself", () => {
    render(<Home />);
    expect(screen.getByText(t.home.expectation)).toBeTruthy();
  });

  test("promises no duration", () => {
    // Any digit-plus-unit, spelled or numeric, in any landing-step copy.
    const copy = [t.tagline, t.home.expectation, t.home.repoLabel, t.home.start].join(" ");
    expect(copy).not.toMatch(/\b\d+\s*(–|-|to)?\s*\d*\s*(second|minute|hour|min|sec)/i);
    expect(copy).not.toMatch(
      /\b(one|two|three|four|five|ten|fifteen|thirty)\b[\s\S]{0,12}\b(second|minute|hour)/i,
    );
  });

  test("does not claim a question count the interview cannot honour", () => {
    // `questions.py` asks 5 core questions plus 1 follow-up for five goal types
    // and 2 for `improve_existing_system` and `debug_issue` — so the real total
    // is six or seven, and "five questions" was the concept's own wrong number.
    expect(t.home.expectation).not.toMatch(/\bfive\s+(short\s+)?questions\b/i);
    expect(t.home.expectation).toMatch(/six or seven/i);
  });
});


/**
 * #1 — the build screen, and why the learner stays on it.
 *
 * Multi-user M7 made `/session/start` return at once, and the first cut of that
 * pushed the learner to the dashboard the moment the id existed. The session was
 * safe, and the experience was not: the answer summary and the live read of their
 * repository were replaced by a card reading "Building your route…".
 *
 * These assert the two halves separately, because they fail independently: that
 * the learner is NOT navigated away while the plan is being built, and that they
 * ARE taken to the session once it is.
 */
describe("after the interview, the learner waits with the build", () => {
  const REPO = "https://github.com/psf/requests";
  const GOAL = { primary_goal: "understand the request lifecycle" };

  /** Walk the repo step, then hand the interview its answer in one go. */
  const reachTheWait = async () => {
    api.checkRepo.mockResolvedValue({ ok: true, reason: null });
    api.goalStart.mockResolvedValue({
      session_id: "g1",
      question: { text: "What are you trying to do?", options: null, index: 1, total: 6 },
    });
    api.goalAnswer.mockResolvedValue({ done: true, goal: GOAL });
    api.sessionStart.mockResolvedValue({ session_id: "s1", status: "generating" });

    render(<Home />);
    await userEvent.type(screen.getByLabelText(t.home.repoLabel), REPO);
    await userEvent.click(screen.getByRole("button", { name: t.home.start }));

    const box = await screen.findByRole("textbox");
    await userEvent.type(box, "the request lifecycle");
    await userEvent.click(screen.getByRole("button", { name: t.goal.continue }));

    // The review gate: the interview shows the answers back and waits. Starting
    // is a separate, explicit act — see `GoalDialogue.test.tsx`.
    await screen.findByText(t.goal.reviewTitle);
    await userEvent.click(screen.getByRole("button", { name: t.goal.startSession }));
  };

  test("stays on the progress screen while the plan is being built", async () => {
    api.getSessionSummary.mockResolvedValue({ session_id: "s1", status: "generating" });
    await reachTheWait();

    // The screen that says what is being read, in their repository.
    await waitFor(() => expect(screen.getByText(t.starting.label)).toBeTruthy());
    // And the goal they confirmed, still on screen (P3's continuity).
    expect(screen.getByText(GOAL.primary_goal)).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });

  test("goes to the welcome page once the plan lands", async () => {
    api.getSessionSummary.mockResolvedValue({ session_id: "s1", status: "active" });
    await reachTheWait();

    await waitFor(() => expect(push).toHaveBeenCalledWith("/session/s1/welcome"));
  });

  test("a failed background plan is reported here, not on the dashboard", async () => {
    // The row is left in a terminal state on every path, so `failed` is a fact
    // and not a timeout — and the learner still has their answers, so the
    // failure screen's "Try again" can re-run without redoing the interview.
    api.getSessionSummary.mockResolvedValue({ session_id: "s1", status: "failed" });
    await reachTheWait();

    await waitFor(() => expect(screen.getByText(t.failed.label)).toBeTruthy());
    expect(screen.getByRole("button", { name: t.failed.tryAgain })).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });

  test("a blip while polling is NOT reported as a failed pipeline", async () => {
    api.getSessionSummary.mockRejectedValue(new Error("server_unreachable"));
    await reachTheWait();

    await waitFor(() => expect(screen.getByText(t.starting.label)).toBeTruthy());
    expect(screen.queryByText(t.failed.label)).toBeNull();
  });
});
