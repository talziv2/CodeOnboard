import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import SurfaceTabs from "@/components/lesson/SurfaceTabs";
import { tabsFor } from "@/lib/surfaceTabs";
import { t } from "@/lib/strings";

/**
 * The bar. Claims worth pinning:
 *
 *   - it CANNOT change the selection, only report a click — which is what makes R5
 *     enforceable somewhere other than by review;
 *   - a mode shows ITS tabs and not the other mode's, which is the whole point of
 *     the switch replacing a flat four-tab bar;
 *   - a dot for a tab that is not on screen escalates to the mode button, or the
 *     signal goes silent for exactly as long as the learner is in the other mode;
 *   - `next`'s bar is unchanged — no modes, two tabs, old label — because it stays
 *     live as the thing `surfaces` is measured against and any difference in it
 *     would be a difference in the comparison.
 */

const group = () => screen.getByRole("group", { name: t.session.modeLabel });
const modeButtons = () => within(group()).getAllByRole("button");
const tabButtons = () => {
  const modes = new Set(screen.queryAllByRole("group").flatMap((g) => within(g).getAllByRole("button")));
  return screen.getAllByRole("button").filter((b) => !modes.has(b));
};
const tabLabels = () => tabButtons().map((b) => b.textContent);
const selected = () =>
  tabButtons().find((b) => b.getAttribute("aria-current") === "page")?.textContent;
const currentMode = () =>
  modeButtons().find((b) => b.getAttribute("aria-pressed") === "true")?.textContent;

const bar = (props: Partial<React.ComponentProps<typeof SurfaceTabs>> = {}) =>
  render(
    <SurfaceTabs
      tabs={tabsFor("surfaces")}
      active="lesson"
      onPick={vi.fn()}
      onSwitchMode={vi.fn()}
      {...props}
    />
  );

describe("two modes, and only one mode's tabs at a time", () => {
  test("learn mode: Learn · Route, then Lesson · Understanding", () => {
    bar();
    expect(modeButtons().map((b) => b.textContent)).toEqual([
      t.session.mode.learn,
      t.session.mode.route,
    ]);
    expect(tabLabels()).toEqual(["Lesson", "Understanding"]);
    expect(currentMode()).toBe(t.session.mode.learn);
  });

  test("route mode: Map · Analysis, and the lesson tabs are gone", () => {
    bar({ active: "map" });
    expect(tabLabels()).toEqual(["Map", "Analysis"]);
    expect(currentMode()).toBe(t.session.mode.route);
  });

  test("the mode follows the active tab rather than being told separately", () => {
    // One source of truth. A `mode` prop beside `active` could disagree with it,
    // and the disagreement would render one mode's tabs around the other's view.
    bar({ active: "analysis" });
    expect(currentMode()).toBe(t.session.mode.route);
    expect(selected()).toBe("Analysis");
  });

  test("the active tab is the one marked current, and only it", () => {
    bar({ active: "understanding" });
    expect(selected()).toBe("Understanding");
    expect(tabButtons().filter((b) => b.getAttribute("aria-current") === "page")).toHaveLength(1);
  });
});

describe("the bar reports, it does not decide", () => {
  test("a tab click reports the tab and changes nothing by itself", async () => {
    const onPick = vi.fn();
    const user = userEvent.setup();
    bar({ onPick });
    await user.click(screen.getByRole("button", { name: "Understanding" }));

    expect(onPick).toHaveBeenCalledWith("understanding");
    // Still Lesson: the bar is told what is active, it does not decide.
    expect(selected()).toBe("Lesson");
  });

  test("a mode click reports the mode and changes nothing by itself", async () => {
    const onSwitchMode = vi.fn();
    const user = userEvent.setup();
    bar({ onSwitchMode });
    await user.click(screen.getByRole("button", { name: t.session.mode.route }));

    expect(onSwitchMode).toHaveBeenCalledWith("route");
    expect(currentMode()).toBe(t.session.mode.learn);
    expect(tabLabels()).toEqual(["Lesson", "Understanding"]);
  });
});

describe("next's bar is untouched", () => {
  test("no mode switch, two tabs, and the map keeps its old label", async () => {
    // The qualifier is keyed to the BUILD, not to how many tabs are up — `surfaces`
    // now has a two-tab state of its own when a chapter overview is open, and the
    // map tab must not rename itself as the learner opens and closes overviews. So
    // this asserts `next`'s copy with `next` actually selected, the same way the
    // canvas tests do it.
    vi.resetModules();
    vi.doMock("@/lib/flags", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@/lib/flags")>()),
      lessonUi: () => "next",
    }));
    const Bar = (await import("@/components/lesson/SurfaceTabs")).default;
    render(
      <Bar tabs={tabsFor("next")} active="lesson" onPick={vi.fn()} onSwitchMode={vi.fn()} />
    );
    expect(screen.queryAllByRole("group")).toHaveLength(0);
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Lesson",
      t.session.tabMap,
    ]);
    vi.doUnmock("@/lib/flags");
    vi.resetModules();
  });
});

describe("surfaces keeps one name for the map, whatever else is up", () => {
  test("both route tabs offered: Map", () => {
    bar({ active: "map" });
    expect(tabLabels()).toEqual(["Map", "Analysis"]);
  });

  test("learn mode reduced to one tab by an overview: the map is still Map", () => {
    bar({ tabs: tabsFor("surfaces", { sectionOverview: true }), active: "map" });
    expect(tabLabels()).toEqual(["Map", "Analysis"]);
  });

  test("and learn mode then holds Lesson alone", () => {
    bar({ tabs: tabsFor("surfaces", { sectionOverview: true }), active: "lesson" });
    expect(tabLabels()).toEqual(["Lesson"]);
    // The switch stays: route mode is still somewhere to go.
    expect(modeButtons()).toHaveLength(2);
  });
});

describe("the dot", () => {
  test("marks a tab that changed while the learner was elsewhere", () => {
    bar({ changed: ["understanding"] });
    expect(screen.getByText(t.session.tabChanged(t.session.tab.understanding))).toBeTruthy();
  });

  test("never appears on the tab being looked at", () => {
    // Reporting a change to the person watching it happen.
    bar({ active: "understanding", changed: ["understanding"] });
    expect(screen.queryByText(t.session.tabChanged(t.session.tab.understanding))).toBeNull();
  });

  test("names the tab it is about, rather than saying only that something changed", () => {
    bar({ active: "understanding", changed: ["lesson"] });
    expect(
      screen.getByText(t.session.tabChanged(t.session.tab.lesson)).textContent
    ).toContain("Lesson");
  });

  test("a change in the other mode is announced by name, though its tab is off screen", () => {
    // The route mark lands on Map while the learner is in learn mode. Announcing
    // "Route has changed" would name the switch rather than the destination.
    bar({ changed: ["map"] });
    expect(screen.getByText(t.session.tabChanged(t.session.tab.map))).toBeTruthy();
  });

  test("and it is drawn on the mode button, which is the only thing on screen", () => {
    const { container } = bar({ changed: ["map"] });
    const route = screen.getByRole("button", { name: t.session.mode.route });
    expect(route.querySelector("span[aria-hidden]")).toBeTruthy();
    // Exactly one dot on the bar: the mode's. Two would be one change reported twice.
    expect(container.querySelectorAll("span[aria-hidden].bg-rust")).toHaveLength(1);
  });

  test("no dot on the mode you are in — its own tabs carry it", () => {
    bar({ changed: ["understanding"] });
    const learn = screen.getByRole("button", { name: new RegExp(t.session.mode.learn) });
    expect(learn.querySelector("span[aria-hidden]")).toBeNull();
    expect(
      screen.getByRole("button", { name: "Understanding" }).querySelector("span[aria-hidden]")
    ).toBeTruthy();
  });

  test("no dot means no announcement", () => {
    bar();
    for (const tab of ["lesson", "understanding", "map", "analysis"]) {
      expect(screen.queryByText(t.session.tabChanged(t.session.tab[tab]))).toBeNull();
    }
  });
});

describe("two levels, two rows", () => {
  /**
   * The hierarchy is stated by the geometry, so the geometry is asserted. Side by
   * side, the switch and the tabs read as four peers with an odd gap in them —
   * which is the flat bar the modes exist to replace.
   */
  test("the switch and the tabs are not in the same row", () => {
    bar();
    const switchRow = group().parentElement!;
    for (const tab of tabButtons()) {
      expect(switchRow.contains(tab)).toBe(false);
    }
  });

  test("the tab row holds nothing but tabs", () => {
    bar({ trailing: <span>Show source</span> });
    const tabRow = tabButtons()[0].parentElement!;
    expect(tabRow.contains(group())).toBe(false);
    expect(tabRow.textContent).not.toContain("Show source");
  });

  test("the trailing group rides the mode row", () => {
    // Session chrome, not a choice between views.
    bar({ trailing: <span>Show source</span> });
    expect(group().parentElement!.textContent).toContain("Show source");
  });
});

describe("the trailing group", () => {
  test("renders where the map hint and Show source live", () => {
    bar({ trailing: <span>Show source</span> });
    expect(screen.getByText("Show source")).toBeTruthy();
  });

  test("falls back to the tab row in the build with no mode row", async () => {
    // `next` draws one row, so the group has nowhere else to go — and losing it
    // there would take `Show source` off screen in that build entirely.
    vi.resetModules();
    vi.doMock("@/lib/flags", async (importOriginal) => ({
      ...(await importOriginal<typeof import("@/lib/flags")>()),
      lessonUi: () => "next",
    }));
    const Bar = (await import("@/components/lesson/SurfaceTabs")).default;
    render(
      <Bar
        tabs={tabsFor("next")}
        active="lesson"
        onPick={vi.fn()}
        onSwitchMode={vi.fn()}
        trailing={<span>Show source</span>}
      />
    );
    expect(screen.queryAllByRole("group")).toHaveLength(0);
    const tabRow = screen.getByRole("button", { name: "Lesson" }).parentElement!;
    expect(tabRow.textContent).toContain("Show source");
    vi.doUnmock("@/lib/flags");
    vi.resetModules();
  });
});
