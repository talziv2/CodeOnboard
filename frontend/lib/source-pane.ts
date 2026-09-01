"use client";

/**
 * The source pane's own slice of the display preferences, plus the geometry
 * helpers the drag handlers need.
 *
 * The read happens in an effect rather than in a lazy initialiser: the server
 * renders the default, so reading storage during the first client render would
 * be a hydration mismatch on the one preference that changes the markup (docked
 * is a grid column, floating is not). The docked *width* has no such problem —
 * it travels as a CSS variable the boot script has already set, so it never
 * flashes.
 */
import { useCallback, useEffect, useState } from "react";
import {
  DEFAULT_SOURCE,
  DEFAULT_TUTOR,
  FLOAT_MIN_H,
  FLOAT_MIN_W,
  applyDockWidth,
  clamp,
  readPrefs,
  writePrefs,
  type FloatRect,
  type PanePrefs,
} from "./prefs";

/**
 * One companion pane's persisted preferences.
 *
 * Parameterised by `which` because there are two panes now and they store the
 * same shape under two keys. The hook is otherwise unchanged, including the
 * effect-not-initialiser read: the server renders the default, so reading storage
 * during the first client render would be a hydration mismatch on the one
 * preference that changes the markup.
 *
 * `applyDockWidth` runs for both, and that is deliberate rather than sloppy —
 * `--source-width` sizes the single dock column, only one pane may occupy it
 * (`lib/panes.ts`), and a learner who dragged that column meant the column rather
 * than whatever happened to be in it at the time.
 */
export function useSourcePane(which: "source" | "tutor" = "source") {
  const [source, setSource] = useState<PanePrefs>(
    which === "tutor" ? DEFAULT_TUTOR : DEFAULT_SOURCE
  );

  useEffect(() => {
    setSource(readPrefs()[which]);
  }, [which]);

  const patch = useCallback((change: Partial<PanePrefs>) => {
    setSource((prev) => ({ ...prev, ...change }));
  }, []);

  // Persist as a reaction to the value, not inside the setter: React may run a
  // state updater twice, and writing to storage from one is a side effect.
  useEffect(() => {
    const stored = readPrefs();
    if (JSON.stringify(stored[which]) === JSON.stringify(source)) return;
    writePrefs({ ...stored, [which]: source });
    applyDockWidth(source.dockWidth);
  }, [source, which]);

  return { source, patch };
}

/** A gap wide enough that a floating pane never sits flush against an edge. */
const MARGIN = 16;

/** A rect that has been resolved against a viewport, so nothing is "unplaced". */
export interface PlacedRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/**
 * Resolve a stored rect against the viewport it is about to be shown in.
 *
 * A never-placed pane lands at the top right, under the header, where the
 * docked pane used to be — so switching modes moves it as little as possible.
 * A placed one is pulled back into view, because the window it was sized on may
 * be gone.
 */
export function placeFloat(rect: FloatRect, vw: number, vh: number): PlacedRect {
  const w = clamp(rect.w, FLOAT_MIN_W, Math.max(FLOAT_MIN_W, vw - MARGIN * 2));
  const h = clamp(rect.h, FLOAT_MIN_H, Math.max(FLOAT_MIN_H, vh - MARGIN * 2));
  const x = rect.x ?? vw - w - MARGIN;
  const y = rect.y ?? MARGIN * 5;
  return {
    w,
    h,
    // Keep at least a sliver on screen in every direction; a pane dragged fully
    // off the edge would be unreachable and would look like it had closed.
    x: clamp(x, MARGIN - w + 80, vw - 80),
    y: clamp(y, 0, Math.max(0, vh - 40)),
  };
}
