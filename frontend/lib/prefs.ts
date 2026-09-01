/**
 * Reader preferences — theme, text size, and how the source pane is shown.
 *
 * These are display settings, not learning state: they live in localStorage and
 * never reach the backend, so they follow the browser rather than the session.
 *
 * Everything here is expressed as an attribute or a variable on `<html>`, which
 * is what lets the preference apply before React hydrates (see the boot script
 * in `app/layout.tsx`) and lets components stay theme-blind.
 */

export type ThemeChoice = "system" | "light" | "dark";
export type TextSize = "small" | "medium" | "large" | "xlarge";

/** Docked: a resizable third column. Floating: a window over the lesson. */
export type PaneMode = "dock" | "float";

/** @deprecated the shape is shared by both companion panes — use `PaneMode`. */
export type SourceMode = PaneMode;

/**
 * Where the floating pane sits, in px. `null` means "never placed" — the pane
 * picks a sensible spot against the viewport on first open rather than storing
 * a guess made on some other screen.
 */
export interface FloatRect {
  x: number | null;
  y: number | null;
  w: number;
  h: number;
}

export interface PanePrefs {
  mode: PaneMode;
  /**
   * Whether the pane is showing. Persisted, and **false by default**: the source
   * used to open with every session whether or not the lesson had sent anyone to
   * it, which spent a third of the width on a file nobody had asked for. It now
   * opens when a citation is clicked, and stays open across sessions once it has
   * been opened — the learner who works with the code beside them keeps it, the
   * learner who does not never sees it.
   *
   * Absent from prefs written before this existed, which `readSource` resolves to
   * the default rather than to `undefined` — an older stored preference must not
   * leave the pane in a state React treats as uncontrolled.
   */
  open: boolean;
  /**
   * In **rem**, not px: the docked column is part of the layout, so it scales
   * with the text-size dial like every other column rather than squeezing
   * enlarged code into fixed-width chrome.
   */
  dockWidth: number;
  /** In **px**: a floating window is placed against the viewport, not the type. */
  float: FloatRect;
}

/**
 * @deprecated The shape is no longer specific to the source pane — the Tutor uses
 * exactly the same one, and only one pane may be docked at a time
 * (`lib/panes.ts`). Retained as an alias so no call site had to churn for a
 * rename that changes nothing.
 */
export type SourcePrefs = PanePrefs;

export const DOCK_MIN_REM = 15;
export const DOCK_MAX_REM = 70;
export const FLOAT_MIN_W = 320;
export const FLOAT_MIN_H = 200;

export interface Prefs {
  theme: ThemeChoice;
  textSize: TextSize;
  source: PanePrefs;
  /**
   * The Tutor pane. Absent from every preference blob written before the Tutor
   * existed, which `readPane` resolves to the default rather than to `undefined`
   * — an older stored preference must not leave a pane in a state React treats as
   * uncontrolled.
   */
  tutor: PanePrefs;
}

export const DEFAULT_SOURCE: PanePrefs = {
  mode: "dock",
  open: false,
  dockWidth: 21.25,
  float: { x: null, y: null, w: 680, h: 620 },
};

/**
 * The Tutor's default float is narrower and taller than the source pane's: a
 * transcript is a column of short paragraphs, where source is wide lines. The
 * DOCKED width is deliberately NOT its own — `dockWidth` is shared through
 * `--source-width`, because only one pane occupies the column at a time and a
 * learner who sized that column meant the column.
 */
export const DEFAULT_TUTOR: PanePrefs = {
  mode: "dock",
  open: false,
  dockWidth: 21.25,
  float: { x: null, y: null, w: 460, h: 640 },
};

export const DEFAULT_PREFS: Prefs = {
  theme: "dark",
  textSize: "medium",
  source: DEFAULT_SOURCE,
  tutor: DEFAULT_TUTOR,
};

export const PANE_MODES: PaneMode[] = ["dock", "float"];

/** @deprecated use `PANE_MODES`. */
export const SOURCE_MODES: PaneMode[] = PANE_MODES;

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Multiplier on the browser's own base font size — see `--ui-scale`. */
export const TEXT_SCALE: Record<TextSize, number> = {
  small: 0.9,
  medium: 1,
  large: 1.125,
  xlarge: 1.25,
};

export const THEME_ORDER: ThemeChoice[] = ["system", "light", "dark"];
export const TEXT_SIZE_ORDER: TextSize[] = ["small", "medium", "large", "xlarge"];

export const PREFS_KEY = "codeonboard:prefs";

/** The single source of truth for `system`, shared with the boot script. */
export function systemTheme(): "light" | "dark" {
  return typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

export function resolveTheme(choice: ThemeChoice): "light" | "dark" {
  return choice === "system" ? systemTheme() : choice;
}

/** Every field is checked, because storage may hold a shape from an older build. */
function readPane(raw: unknown, fallback: PanePrefs): PanePrefs {
  const s = (raw ?? {}) as Partial<PanePrefs>;
  const f = (s.float ?? {}) as Partial<FloatRect>;
  const num = (v: unknown, d: number) =>
    typeof v === "number" && Number.isFinite(v) ? v : d;
  return {
    mode: PANE_MODES.includes(s.mode as PaneMode) ? (s.mode as PaneMode) : fallback.mode,
    // Strict `=== true`, so anything an older or corrupt prefs blob holds here
    // resolves to closed rather than to something truthy.
    open: s.open === true,
    dockWidth: clamp(num(s.dockWidth, fallback.dockWidth), DOCK_MIN_REM, DOCK_MAX_REM),
    float: {
      x: typeof f.x === "number" && Number.isFinite(f.x) ? f.x : null,
      y: typeof f.y === "number" && Number.isFinite(f.y) ? f.y : null,
      w: Math.max(FLOAT_MIN_W, num(f.w, fallback.float.w)),
      h: Math.max(FLOAT_MIN_H, num(f.h, fallback.float.h)),
    },
  };
}

export function readPrefs(): Prefs {
  if (typeof window === "undefined") return DEFAULT_PREFS;
  try {
    const raw = window.localStorage.getItem(PREFS_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    return {
      theme: THEME_ORDER.includes(parsed.theme as ThemeChoice)
        ? (parsed.theme as ThemeChoice)
        : DEFAULT_PREFS.theme,
      textSize: TEXT_SIZE_ORDER.includes(parsed.textSize as TextSize)
        ? (parsed.textSize as TextSize)
        : DEFAULT_PREFS.textSize,
      source: readPane(parsed.source, DEFAULT_SOURCE),
      tutor: readPane(parsed.tutor, DEFAULT_TUTOR),
    };
  } catch {
    /* storage unavailable or corrupt — the defaults are a working app */
    return DEFAULT_PREFS;
  }
}

export function writePrefs(prefs: Prefs) {
  try {
    window.localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* storage unavailable — the preference still applies for this page */
  }
}

/** Stamp the resolved preference onto `<html>`. The CSS does the rest. */
export function applyPrefs(prefs: Prefs) {
  const root = document.documentElement;
  root.dataset.theme = resolveTheme(prefs.theme);
  root.style.setProperty("--ui-scale", String(TEXT_SCALE[prefs.textSize]));
  applyDockWidth(prefs.source.dockWidth);
}

/**
 * The docked column's width, as a variable rather than a React value: dragging
 * the divider writes here on every pointer move, and re-rendering a thousand
 * lines of code sixty times a second is not a resize.
 */
export function applyDockWidth(rem: number) {
  document.documentElement.style.setProperty(
    "--source-width",
    `${clamp(rem, DOCK_MIN_REM, DOCK_MAX_REM)}rem`
  );
}

/** One rem in px, right now — the bridge between pointer deltas and rem widths. */
export function remInPx(): number {
  return parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
}

/**
 * Runs before first paint, inlined into the document head. It must not import
 * anything, so the defaults and the storage key are repeated here — the cost of
 * that duplication is one line each; the cost of skipping it is a flash of the
 * wrong theme on every page load.
 */
export const BOOT_SCRIPT = `
(function () {
  try {
    var p = JSON.parse(localStorage.getItem(${JSON.stringify(PREFS_KEY)}) || "{}");
    var theme = p.theme === "system"
      ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")
      : (p.theme === "light" || p.theme === "dark" ? p.theme : ${JSON.stringify(DEFAULT_PREFS.theme)});
    var scale = ${JSON.stringify(TEXT_SCALE)}[p.textSize] || 1;
    var w = (p.source && typeof p.source.dockWidth === "number")
      ? p.source.dockWidth
      : ${JSON.stringify(DEFAULT_SOURCE.dockWidth)};
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.setProperty("--ui-scale", String(scale));
    document.documentElement.style.setProperty("--source-width", w + "rem");
  } catch (e) {
    document.documentElement.dataset.theme = ${JSON.stringify(DEFAULT_PREFS.theme)};
  }
})();
`;
