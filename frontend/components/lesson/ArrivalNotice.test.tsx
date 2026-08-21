import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import ArrivalNotice from "@/components/lesson/ArrivalNotice";
import type { ArrivalNotice as Notice } from "@/lib/arrival";

/**
 * The sentence, and the two things the learner can do about it.
 *
 * `lib/arrival.test.ts` covers WHICH notice is derived; these cover what is
 * actually on screen for each shape of it — including the case where a number
 * must not be quoted, which is the one a reader would otherwise never see fail.
 */

const notice = (over: Partial<Notice> = {}): Notice => ({
  direction: "ahead",
  position: 9,
  total: 15,
  isStation: true,
  passed: 4,
  revisited: false,
  returnTo: { nodeId: "n1", title: "Understand the Session object", position: 5 },
  ...over,
});

const draw = (over: Partial<Notice> = {}, handlers = {}) =>
  render(
    <ArrivalNotice
      notice={notice(over)}
      onReturn={vi.fn()}
      onDismiss={vi.fn()}
      {...handlers}
    />
  );

describe("what the notice says", () => {
  test("jumping ahead names the stop and how many were passed", () => {
    draw();
    expect(
      screen.getByText("You jumped ahead to stop 9 of 15, passing 4 stops.")
    ).toBeTruthy();
  });

  test("an adjacent jump does not claim any stops were passed", () => {
    draw({ passed: 0 });
    expect(screen.getByText("You jumped ahead to stop 9 of 15.")).toBeTruthy();
  });

  test("coming back to a visited stop says it was already taken", () => {
    draw({ direction: "back", position: 3, revisited: true });
    expect(
      screen.getByText("You came back to stop 3 of 15 — already taken.")
    ).toBeTruthy();
  });

  test("going back to an UNVISITED stop does not claim it was taken", () => {
    draw({ direction: "back", position: 3, revisited: false });
    expect(screen.getByText("You went back to stop 3 of 15.")).toBeTruthy();
  });

  test("with no known direction it reports position and stops there", () => {
    draw({ direction: null, returnTo: null });
    expect(screen.getByText("You jumped to stop 9 of 15.")).toBeTruthy();
  });

  test("a stop the rail does not number gets no number", () => {
    // THE FAILURE THIS PREVENTS: "stop 3 of 4" above three visible stops. The rail
    // counts neither warm-ups nor optional units, so the notice may not either.
    // `passed: 0` is not arbitrary — `arrivalNotice` guarantees it whenever either
    // end is not a station, because the position arithmetic is meaningless there.
    // Asserted in lib/arrival.test.ts; relied on here.
    draw({ isStation: false, passed: 0 });
    const said = screen.getByText(/You jumped ahead to a stop off the default walk/);
    expect(said.textContent).not.toMatch(/\d/);
  });
});

describe("what the learner can do about it", () => {
  test("the way back names where they were, and calls back with its id", async () => {
    const onReturn = vi.fn();
    draw({}, { onReturn });

    await userEvent.click(
      screen.getByRole("button", { name: /Understand the Session object/ })
    );
    expect(onReturn).toHaveBeenCalledWith("n1");
  });

  test("no way back is offered when the stop they left is gone", () => {
    // A button that cannot say where it goes is worse than no button.
    draw({ returnTo: null });
    expect(screen.queryByRole("button", { name: /Return to/ })).toBeNull();
  });

  test("staying put is offered, and reported", async () => {
    const onDismiss = vi.fn();
    draw({}, { onDismiss });

    await userEvent.click(screen.getByRole("button", { name: "Stay here" }));
    expect(onDismiss).toHaveBeenCalled();
  });

  test("while going back, the button says so and refuses a second click", () => {
    draw({}, { returning: true });
    const button = screen.getByRole("button", { name: "Going back…" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });
});
