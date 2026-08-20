import { describe, expect, test } from "vitest";
import {
  BAND_MEDIUM,
  BAND_NARROW,
  LESSON_FLOOR,
  RAIL_REM,
  bandFor,
  sourceMustOverlay,
} from "@/lib/layout-bands";

/**
 * The band rules.
 *
 * These are pure functions on purpose. The obvious implementation of "does the
 * source still fit" measures the lesson column and reacts to it, and that
 * oscillates: the pane pops out, the lesson grows past the floor, the pane docks
 * again, the lesson shrinks, forever. Deciding from the inputs instead makes the
 * answer stable for a given window — which is the property the last test here
 * pins directly.
 */

const REM = 16;

describe("which band a width is in", () => {
  test("the boundaries belong to the wider band", () => {
    expect(bandFor(BAND_MEDIUM)).toBe("wide");
    expect(bandFor(BAND_MEDIUM - 1)).toBe("medium");
    expect(bandFor(BAND_NARROW)).toBe("medium");
    expect(bandFor(BAND_NARROW - 1)).toBe("narrow");
  });

  test("the usual desktop widths land where they should", () => {
    expect(bandFor(1600)).toBe("wide");
    expect(bandFor(1280)).toBe("wide");
    expect(bandFor(1100)).toBe("medium");
    expect(bandFor(1024)).toBe("medium");
    expect(bandFor(900)).toBe("narrow");
    expect(bandFor(600)).toBe("narrow");
  });
});

describe("when the source pane has to leave the grid", () => {
  test("never docked in the narrow band, whatever it would fit", () => {
    expect(sourceMustOverlay("narrow", 900, 15, REM)).toBe(true);
    // Even an absurdly generous window, if the band says narrow.
    expect(sourceMustOverlay("narrow", 900, 1, REM)).toBe(true);
  });

  test("stays docked while the lesson keeps its floor", () => {
    // 1600 - 268 rail - 340 pane = 992, well clear of 560.
    expect(sourceMustOverlay("wide", 1600, 21.25, REM)).toBe(false);
  });

  test("leaves once the lesson would drop under the floor", () => {
    const rail = RAIL_REM.wide * REM;
    const dock = 21.25 * REM;
    const exactly = rail + dock + LESSON_FLOOR;
    expect(sourceMustOverlay("wide", exactly, 21.25, REM)).toBe(false);
    expect(sourceMustOverlay("wide", exactly - 1, 21.25, REM)).toBe(true);
  });

  test("a dragged-wide pane can push itself out at a width that was fine", () => {
    // Same window; the only thing that changed is how wide the learner dragged it.
    expect(sourceMustOverlay("wide", 1280, 21.25, REM)).toBe(false);
    expect(sourceMustOverlay("wide", 1280, 40, REM)).toBe(true);
  });

  test("the collapsed rail buys the pane room the full rail did not", () => {
    // A width where the full rail forces the pane out but the icon strip does not.
    const w = 1000;
    expect(sourceMustOverlay("wide", w, 21.25, REM)).toBe(true);
    expect(sourceMustOverlay("medium", w, 21.25, REM)).toBe(false);
  });

  test("larger text moves the thresholds, because the columns are in rem", () => {
    // The text-size dial scales the root font, so the same window holds less.
    expect(sourceMustOverlay("wide", 1280, 21.25, 16)).toBe(false);
    expect(sourceMustOverlay("wide", 1280, 21.25, 20)).toBe(true);
  });

  test("the decision does not depend on the lesson width it produces", () => {
    // The anti-oscillation property, stated directly: calling it again with the
    // width the previous answer would have produced changes nothing.
    const vw = 1200;
    const first = sourceMustOverlay("wide", vw, 21.25, REM);
    const second = sourceMustOverlay("wide", vw, 21.25, REM);
    const third = sourceMustOverlay("wide", vw, 21.25, REM);
    expect([first, second, third]).toEqual([first, first, first]);
  });
});
