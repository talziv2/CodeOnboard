"use client";

import { useEffect, useState } from "react";

/**
 * How much room the session layout has, as one of three named bands.
 *
 * The session is three columns — route, lesson, source — and the lesson is the
 * one that matters. Before this, all three were laid out unconditionally, so
 * narrowing the window squeezed the reading column between two panels that had
 * no opinion about how little space they were leaving it. The bands make that an
 * explicit decision instead of an accident: the panels give way, in order of how
 * little they are needed at that moment, and the lesson keeps its width.
 *
 *   wide    >= 1180   full rail, source docked
 *   medium  >=  960   rail collapses to an icon strip, source still docked
 *   narrow   <  960   both become overlays; the lesson has the window
 *
 * `LESSON_FLOOR` is the width below which the reading column stops being a
 * reading column. It was derived as the prose measure plus its gutters — then
 * `48ch`, now `46ch` after the reading face changed and `.measure` was
 * re-measured for it (see `app/globals.css`) — because a column narrower than its
 * own text is a column that has stopped doing its job.
 *
 * So 560 now has ~74px of slack over the 486px measure rather than sitting on it.
 * Left at 560 deliberately: the floor only has to be at least the measure, slack
 * costs nothing, and moving a band threshold is a layout decision rather than a
 * consequence of the type. Do not re-derive it from `ch` here — that number is
 * only true of one font, and this is the second time it went stale.
 */
export type Band = "wide" | "medium" | "narrow";

export const BAND_MEDIUM = 1180;
export const BAND_NARROW = 960;
export const LESSON_FLOOR = 560;

/** Rail track widths per band, in rem, matching the grid template. */
export const RAIL_REM = { wide: 19.5, medium: 3.5, narrow: 0 } as const;

export function bandFor(width: number): Band {
  if (width < BAND_NARROW) return "narrow";
  if (width < BAND_MEDIUM) return "medium";
  return "wide";
}

/**
 * Whether the docked source pane would leave the lesson too narrow to read.
 *
 * A pure function of the viewport, the rail track and the pane's own width — NOT
 * of the lesson's measured width. Measuring the lesson and reacting to it is the
 * obvious implementation and it oscillates: the pane pops out, the lesson grows
 * past the floor, the pane docks again, the lesson shrinks. Deciding from the
 * inputs instead gives the same answer every time for the same window.
 */
export function sourceMustOverlay(
  band: Band,
  viewportWidth: number,
  dockWidthRem: number,
  rootFontPx: number
): boolean {
  if (band === "narrow") return true;
  const railPx = RAIL_REM[band] * rootFontPx;
  const dockPx = dockWidthRem * rootFontPx;
  return viewportWidth - railPx - dockPx < LESSON_FLOOR;
}

/**
 * The live viewport width.
 *
 * Starts at 0 rather than at a guess, so the first client render matches the
 * server's — which cannot know the width — and the band is applied once, after
 * mount, instead of flashing the wrong layout. Callers treat 0 as "wide", which
 * is the layout the markup already describes.
 */
export function useViewportWidth(): number {
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const read = () => setWidth(window.innerWidth);
    read();
    window.addEventListener("resize", read);
    return () => window.removeEventListener("resize", read);
  }, []);

  return width;
}

export function useBand(): { width: number; band: Band } {
  const width = useViewportWidth();
  return { width, band: width === 0 ? "wide" : bandFor(width) };
}

/** The root font size in px, which is what `rem` tracks — and the text-size dial moves it. */
export function useRootFontPx(): number {
  const [px, setPx] = useState(16);

  useEffect(() => {
    const read = () =>
      setPx(parseFloat(getComputedStyle(document.documentElement).fontSize) || 16);
    read();
    // The dial writes `--ui-scale` on <html>, so watch the attribute it lands on
    // rather than polling.
    const obs = new MutationObserver(read);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["style"] });
    window.addEventListener("resize", read);
    return () => {
      obs.disconnect();
      window.removeEventListener("resize", read);
    };
  }, []);

  return px;
}
