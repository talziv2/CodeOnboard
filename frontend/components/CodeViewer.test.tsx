import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import CodeViewer from "@/components/CodeViewer";
import { DOCK_MAX_REM, DOCK_MIN_REM, FLOAT_MIN_W, type SourcePrefs } from "@/lib/prefs";
import { t } from "@/lib/strings";

/**
 * The source pane's two modes, and the gestures that size them.
 *
 * Written because this regressed silently and nothing caught it. An earlier
 * revision had a third rendering — an "overlay" — which forced `mode: "dock"`,
 * pinned the pane to a fixed `max-w`, and laid a full-bleed backdrop button over
 * the page. All three of the learner's complaints were that one branch: undocking
 * did nothing (the mode was overridden), resizing did nothing (the width was
 * fixed), and the rest of the screen was dead (the backdrop swallowed every
 * click). The branch is gone; these tests are what keeps it gone.
 *
 * The claims are behavioural, not visual. A test that asserted class names would
 * have passed against the overlay too — it had all the right classes.
 */

vi.mock("@/lib/api", () => ({
  getFile: vi.fn(async () => ({ content: "one\ntwo\nthree\n" })),
}));

// Shiki tokenises asynchronously and none of it is under test here.
vi.mock("@/components/CodeLines", () => ({
  default: () => <pre data-testid="code">one</pre>,
}));

const SOURCE: SourcePrefs = {
  mode: "dock",
  open: true,
  dockWidth: 30,
  float: { x: null, y: null, w: 680, h: 620 },
};

function view(source: Partial<SourcePrefs> = {}) {
  const onSourceChange = vi.fn();
  const onClose = vi.fn();
  const utils = render(
    <CodeViewer
      sessionId="s1"
      filePath="requests/adapters.py"
      highlightStart={153}
      highlightEnd={155}
      focusKey={1}
      source={{ ...SOURCE, ...source }}
      onSourceChange={onSourceChange}
      onClose={onClose}
    />
  );
  return { ...utils, onSourceChange, onClose };
}

beforeEach(() => {
  // jsdom implements neither, and `begin` calls capture before recording the
  // gesture — so without these every drag test would silently test nothing.
  Element.prototype.setPointerCapture = vi.fn();
  Element.prototype.releasePointerCapture = vi.fn();
});

// `getFile` is mocked async, so most tests here finish before it settles and the
// resulting `setContent` lands outside anyone's `act`. Flushed rather than
// silenced: the load is real, it just is not what these tests are about.
afterEach(async () => {
  await act(async () => {});
});

describe("the two modes are two renderings, not one with a lid on it", () => {
  test("docked is a column: no dialog, and nothing covering the page", () => {
    const { container } = view({ mode: "dock" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(container.querySelector("aside")).toBeTruthy();
    // The overlay's backdrop was a `fixed inset-0` button. A docked column has no
    // business rendering anything that spans the viewport.
    expect(container.querySelector(".fixed.inset-0")).toBeNull();
  });

  test("floating is a window the page can be used around", () => {
    view({ mode: "float" });
    const win = screen.getByRole("dialog", { name: t.source.window });
    // NOT `aria-modal`. The learner asked for the rest of the screen back, and a
    // modal dialog is a promise to assistive tech that the rest is unavailable —
    // which is the same lie the backdrop told with pointer events.
    expect(win.getAttribute("aria-modal")).toBeNull();
  });

  test("both modes offer both modes — the current one is the pressed one", () => {
    for (const mode of ["dock", "float"] as const) {
      const { unmount } = view({ mode });
      const dock = screen.getByRole("button", { name: t.source.dock });
      const float = screen.getByRole("button", { name: t.source.float });
      expect(dock.getAttribute("aria-pressed")).toBe(String(mode === "dock"));
      expect(float.getAttribute("aria-pressed")).toBe(String(mode === "float"));
      unmount();
    }
  });

  test("undocking asks for float and nothing else", () => {
    const { onSourceChange } = view({ mode: "dock" });
    fireEvent.click(screen.getByRole("button", { name: t.source.float }));
    expect(onSourceChange).toHaveBeenCalledWith({ mode: "float" });
  });

  test("re-docking asks for dock", () => {
    const { onSourceChange } = view({ mode: "float" });
    fireEvent.click(screen.getByRole("button", { name: t.source.dock }));
    expect(onSourceChange).toHaveBeenCalledWith({ mode: "dock" });
  });
});

describe("the docked column is resizable", () => {
  test("the divider is a separator, reachable and labelled", () => {
    view({ mode: "dock" });
    const sep = screen.getByRole("separator", { name: t.source.resize });
    expect(sep.getAttribute("aria-orientation")).toBe("vertical");
    expect(sep.getAttribute("tabindex")).toBe("0");
  });

  test("arrow keys commit a width — the pane is on the trailing edge, so left widens", () => {
    const { onSourceChange } = view({ mode: "dock", dockWidth: 30 });
    const sep = screen.getByRole("separator", { name: t.source.resize });

    fireEvent.keyDown(sep, { key: "ArrowLeft" });
    const widened = onSourceChange.mock.calls[0][0].dockWidth;
    expect(widened).toBeGreaterThan(30);

    onSourceChange.mockClear();
    fireEvent.keyDown(sep, { key: "ArrowRight" });
    expect(onSourceChange.mock.calls[0][0].dockWidth).toBeLessThan(30);
  });

  test("a nudge past either end clamps instead of running away", () => {
    const atMax = view({ mode: "dock", dockWidth: DOCK_MAX_REM });
    fireEvent.keyDown(screen.getByRole("separator", { name: t.source.resize }), {
      key: "ArrowLeft",
    });
    expect(atMax.onSourceChange).toHaveBeenCalledWith({ dockWidth: DOCK_MAX_REM });
    atMax.unmount();

    const atMin = view({ mode: "dock", dockWidth: DOCK_MIN_REM });
    fireEvent.keyDown(screen.getByRole("separator", { name: t.source.resize }), {
      key: "ArrowRight",
    });
    expect(atMin.onSourceChange).toHaveBeenCalledWith({ dockWidth: DOCK_MIN_REM });
  });

  test("a key that is not a resize is left alone", () => {
    const { onSourceChange } = view({ mode: "dock" });
    fireEvent.keyDown(screen.getByRole("separator", { name: t.source.resize }), { key: "Enter" });
    expect(onSourceChange).not.toHaveBeenCalled();
  });
});

describe("the floating window is resizable from every edge and corner", () => {
  /** The grips are `aria-hidden` decorations; their classes say which edge. */
  const grips = (win: HTMLElement) => [...win.querySelectorAll("[aria-hidden].absolute")];

  /**
   * jsdom's `PointerEvent` does not carry `clientX`/`clientY`, and this gesture is
   * nothing but deltas — fired as pointer events it computes `NaN` and every
   * assertion below would compare `NaN` to `NaN` and look like a pass waiting to
   * happen. `MouseEvent` carries the coordinates, and React dispatches by event
   * type, so the component's `onPointer*` handlers still receive these.
   */
  const at = (el: Element, type: string, clientX: number, clientY: number) =>
    fireEvent(el, new MouseEvent(type, { clientX, clientY, bubbles: true }));

  test("eight grips: four edges, four corners", () => {
    view({ mode: "float" });
    const cursors = grips(screen.getByRole("dialog")).map(
      (g) => (g.className.match(/cursor-[\w-]+/) ?? [""])[0]
    );
    expect(cursors).toHaveLength(8);
    expect(new Set(cursors)).toEqual(
      new Set([
        "cursor-ns-resize",
        "cursor-ew-resize",
        "cursor-nwse-resize",
        "cursor-nesw-resize",
      ])
    );
  });

  test("dragging the east edge commits a wider window", async () => {
    const { onSourceChange } = view({ mode: "float" });
    const win = screen.getByRole("dialog");
    // The gesture measures the element rather than trusting the last commit, so
    // the box has to answer.
    win.getBoundingClientRect = () =>
      ({ left: 500, top: 80, width: 680, height: 620 }) as DOMRect;
    const east = grips(win).find((g) => /right-0/.test(g.className) && /inset-y-0/.test(g.className));
    expect(east).toBeTruthy();

    at(east!, "pointerdown", 1180, 390);
    at(win, "pointermove", 1280, 390);
    at(win, "pointerup", 1280, 390);

    await waitFor(() => expect(onSourceChange).toHaveBeenCalled());
    expect(onSourceChange.mock.calls[0][0].float.w).toBeGreaterThan(680);
  });

  test("dragging an edge inward stops at the minimum rather than collapsing", async () => {
    const { onSourceChange } = view({ mode: "float" });
    const win = screen.getByRole("dialog");
    win.getBoundingClientRect = () =>
      ({ left: 500, top: 80, width: 680, height: 620 }) as DOMRect;
    const east = grips(win).find((g) => /right-0/.test(g.className) && /inset-y-0/.test(g.className));

    at(east!, "pointerdown", 1180, 390);
    // Far past the left edge of the window itself.
    at(win, "pointermove", 100, 390);
    at(win, "pointerup", 100, 390);

    await waitFor(() => expect(onSourceChange).toHaveBeenCalled());
    expect(onSourceChange.mock.calls[0][0].float.w).toBe(FLOAT_MIN_W);
  });

  test("the window is moved by its header, but not by the controls in it", async () => {
    const { onSourceChange } = view({ mode: "float" });
    const win = screen.getByRole("dialog");
    win.getBoundingClientRect = () =>
      ({ left: 500, top: 80, width: 680, height: 620 }) as DOMRect;

    // A mode button is `data-no-drag`: clicking it must not also drag the window.
    at(screen.getByRole("button", { name: t.source.dock }), "pointerdown", 900, 90);
    at(win, "pointermove", 960, 150);
    at(win, "pointerup", 960, 150);
    expect(onSourceChange).not.toHaveBeenCalled();
  });
});

describe("what the pane says while it has nothing to show", () => {
  test("the file path and the highlighted band are named in both modes", async () => {
    for (const mode of ["dock", "float"] as const) {
      const { unmount } = view({ mode });
      expect(screen.getByText("requests/adapters.py")).toBeTruthy();
      expect(screen.getByText("153–155")).toBeTruthy();
      await waitFor(() => expect(screen.getByTestId("code")).toBeTruthy());
      unmount();
    }
  });

  test("closing is offered, and is the caller's decision", () => {
    const { onClose } = view();
    fireEvent.click(screen.getByRole("button", { name: t.session.hideSource }));
    expect(onClose).toHaveBeenCalled();
  });
});
