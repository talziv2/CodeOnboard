import { render } from "@testing-library/react";
import { act } from "react";
import { describe, expect, test } from "vitest";

import LessonWorkspace from "@/components/lesson/LessonWorkspace";

/**
 * The collapse is a state machine driven by one number, and the bug it shipped
 * with was not in either state but in the crossing between them: a single
 * threshold plus a layout that moves `scrollTop` when the fold changes size gave
 * the header a coordinate it kept bouncing across.
 *
 * jsdom has no layout, so what can be tested here is the RULE, not the geometry —
 * the dead band, and the attribute the fix hangs on. The geometry was measured in
 * a real engine and is written down in the component's own note.
 */
const scrollerOf = (el: HTMLElement) => {
  let box: HTMLElement | null = el.parentElement;
  while (box && getComputedStyle(box).overflowY !== "auto") box = box.parentElement;
  return box!;
};

/** jsdom stores no scroll offset, so give the node a real, writable one. */
const makeScrollable = (box: HTMLElement) => {
  let top = 0;
  Object.defineProperty(box, "scrollTop", {
    configurable: true,
    get: () => top,
    set: (v: number) => {
      top = v;
    },
  });
  return (to: number) => {
    act(() => {
      box.scrollTop = to;
      box.dispatchEvent(new Event("scroll"));
    });
  };
};

const mount = () => {
  render(
    <div style={{ overflowY: "auto" }}>
      <LessonWorkspace brief={(collapsed) => <span>{collapsed ? "folded" : "open"}</span>}>
        <p>canvas</p>
      </LessonWorkspace>
    </div>
  );
  const brief = document.querySelector("[data-lesson-brief]") as HTMLElement;
  return { brief, scrollTo: makeScrollable(scrollerOf(brief)) };
};

const state = () =>
  (document.querySelector("[data-lesson-brief]") as HTMLElement).dataset.collapsed;

describe("the brief's collapse", () => {
  test("starts open, and stays open through a nudge", () => {
    const { scrollTo } = mount();
    expect(state()).toBe("false");

    scrollTo(40);
    expect(state()).toBe("false");
  });

  test("folds once the scroll is unmistakable", () => {
    const { scrollTo } = mount();

    scrollTo(60);
    expect(state()).toBe("true");
  });

  test("HYSTERESIS: folded, it holds through the coordinate that folded it", () => {
    const { scrollTo } = mount();
    scrollTo(60);

    // This is the flicker, expressed as a rule. The old single threshold read 40
    // as "open" on the way back and 60 as "folded" on the way in, so a scroll
    // hovering between them — or a layout shift landing there — swapped the
    // header on every event.
    scrollTo(40);
    expect(state()).toBe("true");
    scrollTo(20);
    expect(state()).toBe("true");
  });

  test("and unfolds only near the top", () => {
    const { scrollTo } = mount();
    scrollTo(60);

    scrollTo(8);
    expect(state()).toBe("false");
  });

  test("SCROLL ANCHORING is off for the subtree, which is what makes the band hold", () => {
    mount();

    // The class, not the computed value: `css: false` in the test config means
    // jsdom never resolves Tailwind. What is asserted is that the declaration is
    // still on the element that needs it — a future refactor moving it silently
    // brings the flicker back.
    const root = document.querySelector("[data-lesson-brief]")!.parentElement!;
    expect(root.className).toContain("[overflow-anchor:none]");
  });
});
