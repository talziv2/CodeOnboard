import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import SessionMenu from "@/components/SessionMenu";
import { t } from "@/lib/strings";

/**
 * The session menu.
 *
 * Three things are load-bearing. Every session-level action has to actually be in
 * here — they were removed from the header to give the goal its width back, so a
 * missing one is not a tidier header, it is a lost capability.
 *
 * `Start over` and `Rebuild learning path` must stay TWO items doing two different
 * things. They were one, and it was the wrong one: `Start over` re-ran the whole
 * pipeline and came back with a different route. A test that let them collapse
 * back together would let the original defect back in.
 *
 * And all three destructive actions must be confirmed, with only one confirmation
 * open at a time — they sit within a click of each other, and the difference
 * between them is minutes, money, and whether the route survives.
 */

const props = () => ({
  stopCount: 15,
  scoping: false,
  scopeNote: null as string | null,
  onScope: vi.fn(),
  onBriefing: vi.fn(),
  onStartOver: vi.fn(),
  startingOver: false,
  onRebuild: vi.fn(),
  rebuilding: false,
  onFinish: vi.fn(),
});

let p: ReturnType<typeof props>;

beforeEach(() => {
  p = props();
});

const open = async (over: Partial<ReturnType<typeof props>> = {}) => {
  render(<SessionMenu {...p} {...over} />);
  await userEvent.click(screen.getByRole("button", { name: t.session.menu }));
};

describe("what the menu holds", () => {
  test("nothing is on screen until it is opened", () => {
    render(<SessionMenu {...p} />);
    expect(screen.queryByText(t.session.finish)).toBeNull();
    expect(screen.queryByText(t.welcome.headerLink)).toBeNull();
  });

  test("every session action is present", async () => {
    await open();

    expect(screen.getByRole("button", { name: t.scope.shorter })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.scope.deeper })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.welcome.headerLink })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.session.startOver })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.session.rebuild })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.session.finish })).toBeTruthy();
  });

  test("starting over and rebuilding are separate items", async () => {
    // These being one action was the defect this phase exists to fix.
    await open();

    expect(screen.getByRole("button", { name: t.session.startOver })).not.toBe(
      screen.getByRole("button", { name: t.session.rebuild })
    );
  });

  test("scope reports the live stop count and passes the direction through", async () => {
    await open();
    expect(screen.getByText(t.scope.label(15))).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: t.scope.shorter }));
    expect(p.onScope).toHaveBeenCalledWith("shorter");

    await userEvent.click(screen.getByRole("button", { name: t.scope.deeper }));
    expect(p.onScope).toHaveBeenCalledWith("deeper");
  });

  test("a scope result is reported where the control is", async () => {
    await open({ scopeNote: t.scope.nothingShorter });
    expect(screen.getByText(t.scope.nothingShorter)).toBeTruthy();
  });

  test("opening the source is not in here, in either direction", async () => {
    // Neither half. Opening the code beside a lesson is part of reading the
    // lesson, not session management, so its control is in the lesson bar where
    // it can be found without knowing this menu exists. And the pane owns its
    // own close, so there is no Hide half anywhere.
    await open();
    expect(screen.queryByText(t.session.showSource)).toBeNull();
    expect(screen.queryByText(t.session.hideSource)).toBeNull();
  });
});

describe("starting over", () => {
  test("asks first, and says what survives", async () => {
    await open();

    await userEvent.click(screen.getByRole("button", { name: t.session.startOver }));

    expect(p.onStartOver).not.toHaveBeenCalled();
    expect(screen.getByText(t.session.startOverConfirm)).toBeTruthy();
    expect(screen.getByRole("button", { name: t.session.startOverNo })).toBeTruthy();
  });

  test("confirming fires it, and the menu gets out of the way", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: t.session.startOver }));

    await userEvent.click(screen.getByRole("button", { name: t.session.startOverYes }));

    expect(p.onStartOver).toHaveBeenCalledTimes(1);
    expect(p.onRebuild).not.toHaveBeenCalled();
    expect(screen.queryByText(t.session.startOverConfirm)).toBeNull();
  });

  test("backing out leaves the session alone", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: t.session.startOver }));

    await userEvent.click(screen.getByRole("button", { name: t.session.startOverNo }));

    expect(p.onStartOver).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: t.session.startOver })).toBeTruthy();
  });

  test("a reset already running cannot be fired again", async () => {
    await open({ startingOver: true });

    const item = screen.getByRole("button", { name: t.session.startingOver });
    expect(item.hasAttribute("disabled")).toBe(true);
    await userEvent.click(item);
    expect(p.onStartOver).not.toHaveBeenCalled();
  });
});

describe("rebuilding the learning path", () => {
  test("asks first, and the confirmation states the wait", async () => {
    await open();

    await userEvent.click(screen.getByRole("button", { name: t.session.rebuild }));

    expect(p.onRebuild).not.toHaveBeenCalled();
    expect(screen.getByText(t.session.rebuildConfirm)).toBeTruthy();
    // Someone about to spend two to four minutes should be told before they do.
    expect(t.session.rebuildConfirm).toMatch(/two to four minutes/);
  });

  test("confirming fires the rebuild and nothing else", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: t.session.rebuild }));

    await userEvent.click(screen.getByRole("button", { name: t.session.rebuildYes }));

    expect(p.onRebuild).toHaveBeenCalledTimes(1);
    expect(p.onStartOver).not.toHaveBeenCalled();
  });

  test("a rebuild in flight disables both route actions", async () => {
    // They act on the same session; a reset landing mid-rebuild would race two
    // writers against one graph.
    await open({ rebuilding: true });

    expect(
      screen.getByRole("button", { name: t.session.rebuilding }).hasAttribute("disabled")
    ).toBe(true);
    expect(
      screen.getByRole("button", { name: t.session.startOver }).hasAttribute("disabled")
    ).toBe(true);
  });
});

describe("one confirmation at a time", () => {
  test("opening a second confirmation replaces the first", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: t.session.startOver }));
    expect(screen.getByText(t.session.startOverConfirm)).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: t.session.rebuild }));

    expect(screen.getByText(t.session.rebuildConfirm)).toBeTruthy();
    expect(screen.queryByText(t.session.startOverConfirm)).toBeNull();
  });

  test("reopening the menu does not leave a confirmation standing", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: t.session.startOver }));

    await userEvent.click(screen.getByRole("button", { name: t.session.menu }));
    await userEvent.click(screen.getByRole("button", { name: t.session.menu }));

    expect(screen.queryByText(t.session.startOverConfirm)).toBeNull();
    expect(screen.getByRole("button", { name: t.session.startOver })).toBeTruthy();
  });

  test("Escape closes the menu without firing anything", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: t.session.startOver }));

    await userEvent.keyboard("{Escape}");

    expect(p.onStartOver).not.toHaveBeenCalled();
    expect(screen.queryByText(t.session.startOverConfirm)).toBeNull();
    expect(screen.queryByText(t.session.startOver)).toBeNull();
  });
});

describe("finishing the session", () => {
  test("asks first, and says what survives", async () => {
    await open();

    await userEvent.click(screen.getByRole("button", { name: t.session.finish }));

    expect(p.onFinish).not.toHaveBeenCalled();
    expect(screen.getByText(t.session.finishConfirm)).toBeTruthy();
    expect(screen.getByRole("button", { name: t.session.finishYes })).toBeTruthy();
  });

  test("confirming is what ends it", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: t.session.finish }));

    await userEvent.click(screen.getByRole("button", { name: t.session.finishYes }));

    expect(p.onFinish).toHaveBeenCalledTimes(1);
  });

  test("backing out leaves the session alone", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: t.session.finish }));

    await userEvent.click(screen.getByRole("button", { name: t.session.finishNo }));

    expect(p.onFinish).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: t.session.finish })).toBeTruthy();
    expect(screen.queryByText(t.session.finishConfirm)).toBeNull();
  });
});
