import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import SurfaceTabs from "@/components/lesson/SurfaceTabs";
import { tabsFor } from "@/lib/surfaceTabs";
import { t } from "@/lib/strings";

/**
 * The bar. Two claims worth pinning:
 *
 *   - it CANNOT change the tab, only report a click — which is what makes R5
 *     enforceable somewhere other than by review;
 *   - `next`'s bar is unchanged, because it stays live as the thing `surfaces` is
 *     measured against and a relabel would be a difference in the comparison that
 *     has nothing to do with the comparison.
 */

const selected = () =>
  screen.getAllByRole("button").find((b) => b.getAttribute("aria-current") === "page")
    ?.textContent;

describe("the three-tab bar", () => {
  test("Lesson · Understanding · Map, in that order", () => {
    render(<SurfaceTabs tabs={tabsFor("surfaces")} active="lesson" onPick={vi.fn()} />);
    const labels = screen.getAllByRole("button").map((b) => b.textContent);
    expect(labels).toEqual(["Lesson", "Understanding", "Map"]);
  });

  test("the active tab is the one marked current, and only it", () => {
    render(<SurfaceTabs tabs={tabsFor("surfaces")} active="understanding" onPick={vi.fn()} />);
    expect(selected()).toBe("Understanding");
    expect(
      screen.getAllByRole("button").filter((b) => b.getAttribute("aria-current") === "page")
    ).toHaveLength(1);
  });

  test("a click reports the tab and changes nothing by itself", async () => {
    const onPick = vi.fn();
    const user = userEvent.setup();
    render(<SurfaceTabs tabs={tabsFor("surfaces")} active="lesson" onPick={onPick} />);
    await user.click(screen.getByRole("button", { name: "Understanding" }));

    expect(onPick).toHaveBeenCalledWith("understanding");
    // Still Lesson: the bar is told what is active, it does not decide.
    expect(selected()).toBe("Lesson");
  });
});

describe("next's bar is untouched", () => {
  test("two tabs, and the map keeps its old label", async () => {
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
    render(<Bar tabs={tabsFor("next")} active="lesson" onPick={vi.fn()} />);
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Lesson",
      t.session.tabMap,
    ]);
    vi.doUnmock("@/lib/flags");
    vi.resetModules();
  });
});

describe("surfaces keeps one name for the map, however many tabs are up", () => {
  test("three tabs: Map", () => {
    render(<SurfaceTabs tabs={tabsFor("surfaces")} active="lesson" onPick={vi.fn()} />);
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Lesson",
      "Understanding",
      "Map",
    ]);
  });

  test("two tabs, because an overview is open: still Map", () => {
    render(
      <SurfaceTabs
        tabs={tabsFor("surfaces", { sectionOverview: true })}
        active="lesson"
        onPick={vi.fn()}
      />
    );
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Lesson",
      "Map",
    ]);
  });
});

describe("the dot", () => {
  test("marks a tab that changed while the learner was elsewhere", () => {
    render(
      <SurfaceTabs
        tabs={tabsFor("surfaces")}
        active="lesson"
        changed={["understanding"]}
        onPick={vi.fn()}
      />
    );
    expect(
      screen.getByText(t.session.tabChanged(t.session.tab.understanding))
    ).toBeTruthy();
  });

  test("never appears on the tab being looked at", () => {
    // Reporting a change to the person watching it happen.
    render(
      <SurfaceTabs
        tabs={tabsFor("surfaces")}
        active="understanding"
        changed={["understanding"]}
        onPick={vi.fn()}
      />
    );
    expect(
      screen.queryByText(t.session.tabChanged(t.session.tab.understanding))
    ).toBeNull();
  });

  test("names the tab it is about, rather than saying only that something changed", () => {
    render(
      <SurfaceTabs
        tabs={tabsFor("surfaces")}
        active="understanding"
        changed={["lesson"]}
        onPick={vi.fn()}
      />
    );
    const note = screen.getByText(t.session.tabChanged(t.session.tab.lesson));
    expect(note.textContent).toContain("Lesson");
  });

  test("no dot means no announcement", () => {
    render(<SurfaceTabs tabs={tabsFor("surfaces")} active="lesson" onPick={vi.fn()} />);
    for (const tab of ["lesson", "understanding", "map"]) {
      expect(screen.queryByText(t.session.tabChanged(t.session.tab[tab]))).toBeNull();
    }
  });
});

describe("the trailing group", () => {
  test("renders where the map hint and Show source live", () => {
    render(
      <SurfaceTabs
        tabs={tabsFor("surfaces")}
        active="lesson"
        onPick={vi.fn()}
        trailing={<span>Show source</span>}
      />
    );
    expect(screen.getByText("Show source")).toBeTruthy();
  });
});
