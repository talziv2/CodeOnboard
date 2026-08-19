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

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const api = vi.hoisted(() => ({
  checkRepo: vi.fn(),
  sessionStart: vi.fn(),
  goalStart: vi.fn(),
  goalAnswer: vi.fn(),
  goalBack: vi.fn(),
}));
vi.mock("@/lib/api", () => api);

import Home from "@/app/page";

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
