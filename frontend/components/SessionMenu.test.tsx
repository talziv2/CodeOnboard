import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import SessionMenu from "@/components/SessionMenu";
import { t } from "@/lib/strings";

/**
 * The session menu.
 *
 * Two things are load-bearing. Every session-level action has to actually be in
 * here — they were removed from the header to give the goal its width back, so a
 * missing one is not a tidier header, it is a lost capability. And `Finish
 * session` has to be confirmed: it is the one action that ends the thing the
 * learner came for, and it now sits one click from the top of the page rather
 * than at the bottom of a lesson.
 */

const props = () => ({
  stopCount: 15,
  scoping: false,
  scopeNote: null as string | null,
  onScope: vi.fn(),
  onBriefing: vi.fn(),
  onStartOver: vi.fn(),
  restarting: false,
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

  test("all four session actions are present, and nothing else", async () => {
    await open();

    expect(screen.getByRole("button", { name: t.scope.shorter })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.scope.deeper })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.welcome.headerLink })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.session.startOver })).toBeTruthy();
    expect(screen.getByRole("button", { name: t.session.finish })).toBeTruthy();
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
    // Back to the plain item, ready to be asked again.
    expect(screen.getByRole("button", { name: t.session.finish })).toBeTruthy();
    expect(screen.queryByText(t.session.finishConfirm)).toBeNull();
  });

  test("reopening the menu does not leave the confirmation standing", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: t.session.finish }));
    expect(screen.getByText(t.session.finishConfirm)).toBeTruthy();

    // Close and reopen.
    await userEvent.click(screen.getByRole("button", { name: t.session.menu }));
    await userEvent.click(screen.getByRole("button", { name: t.session.menu }));

    expect(screen.queryByText(t.session.finishConfirm)).toBeNull();
    expect(screen.getByRole("button", { name: t.session.finish })).toBeTruthy();
  });

  test("Escape closes the menu without finishing anything", async () => {
    await open();
    await userEvent.click(screen.getByRole("button", { name: t.session.finish }));

    await userEvent.keyboard("{Escape}");

    expect(p.onFinish).not.toHaveBeenCalled();
    expect(screen.queryByText(t.session.finishConfirm)).toBeNull();
    expect(screen.queryByText(t.session.finish)).toBeNull();
  });
});
