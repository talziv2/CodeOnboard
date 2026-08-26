import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import type { SessionGraph } from "@/lib/api";
import { node } from "@/test/factories";
import CompletionScreen from "@/components/lesson/CompletionScreen";
import { t } from "@/lib/strings";

/**
 * #9 — the completion screen IS the confirmation, so it has to be leaveable.
 *
 * `Finish session early` is one unconfirmed click on a quiet link at the foot of
 * every lesson, and `Finish session` is one item in the header menu. Neither
 * writes anything: the flag is client state and no request is made. So the screen
 * was showing an ending that had not happened, with no way to un-see it — the
 * only routes on were a NEW session or the front door, both of which abandon the
 * one the learner was mid-way through.
 *
 * The asymmetry is the design and is what these assert: a way back exists exactly
 * when the learner CHOSE to stop, and never when the walk itself ran out, because
 * then there is nothing to go back to.
 */

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const graph = (): SessionGraph => ({
  session_id: "s1",
  repo_url: "https://github.com/psf/requests",
  goal: {},
  current_node_id: "n1",
  nodes: [
    node("n1", { understanding: "strength", understanding_state: "understood" }),
    node("n2", { understanding: "unresolved" }),
  ],
  edges: [],
  readiness: 0.5,
  progress: {} as never,
  understanding: {} as never,
});

const props = {
  graph: graph(),
  onNewSession: vi.fn(),
  onFinish: vi.fn(),
};

describe("backing out of finishing early", () => {
  test("offers the way back, and leads with it", async () => {
    const onResume = vi.fn();
    render(<CompletionScreen {...props} onResume={onResume} />);

    const back = screen.getByRole("button", { name: t.completion.keepGoing });
    expect(back).toBeTruthy();

    // FIRST in the row. Nothing has been committed, and the two buttons beside it
    // both leave the session — so the reversible option is the one that leads.
    const row = back.parentElement!;
    expect(row.firstElementChild).toBe(back);

    await userEvent.click(back);
    expect(onResume).toHaveBeenCalled();
    // And it changed nothing else: leaving is still the learner's to choose.
    expect(props.onFinish).not.toHaveBeenCalled();
    expect(props.onNewSession).not.toHaveBeenCalled();
  });

  test("says plainly that nothing has been ended", async () => {
    render(<CompletionScreen {...props} onResume={vi.fn()} />);
    expect(screen.getByText(t.completion.notFinishedYet)).toBeTruthy();
  });

  test("a walk that RAN OUT gets no way back — there is nowhere to go", async () => {
    // The other half. A "keep going" button pointing at a finished route would be
    // an offer the session cannot honour.
    render(<CompletionScreen {...props} />);

    expect(screen.queryByRole("button", { name: t.completion.keepGoing })).toBeNull();
    expect(screen.queryByText(t.completion.notFinishedYet)).toBeNull();
    // And the row is exactly what it always was.
    expect(screen.getByRole("button", { name: t.completion.newSession })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.completion.goHome })).toBeTruthy();
  });

  test("the recap is the same either way — it is what the learner is deciding about", async () => {
    render(<CompletionScreen {...props} onResume={vi.fn()} />);
    // What is still unresolved, which is the fact worth seeing before choosing.
    expect(screen.getByText(t.completion.anotherPass(1))).toBeTruthy();
  });
});
