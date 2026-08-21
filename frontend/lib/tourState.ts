/**
 * Whether this browser has been shown the tour, and which one-off tips it has
 * seen.
 *
 * Its own key rather than a field on `prefs`. That module is the display settings
 * a learner CHOOSES from a menu — theme, text size, the source pane — and it is
 * duplicated into the boot script that runs before paint; "have I been shown this"
 * is neither a choice nor anything the first paint depends on. Folding it in would
 * put tutorial bookkeeping in the panel where somebody looks for a theme switch.
 *
 * Per browser rather than per session, and never sent to the backend: the tour
 * teaches the interface, and the interface is the same in every session. Somebody
 * who has taken it once should not meet it again on their second repository.
 */

export const TOUR_KEY = "codeonboard:tour";

export interface TourRecord {
  /** The workspace walk has been finished or skipped. */
  readonly done: boolean;
  /** Ids of the just-in-time tips already shown. */
  readonly tips: readonly string[];
}

export const NO_TOUR: TourRecord = { done: false, tips: [] };

export function readTour(): TourRecord {
  if (typeof window === "undefined") return NO_TOUR;
  try {
    const raw = window.localStorage.getItem(TOUR_KEY);
    if (!raw) return NO_TOUR;
    const parsed = JSON.parse(raw) as Partial<TourRecord>;
    return {
      // Strict `=== true`, so a shape from an older build resolves to "not yet
      // shown" rather than to something truthy that silently suppresses the tour.
      done: parsed.done === true,
      tips: Array.isArray(parsed.tips) ? parsed.tips.filter((t) => typeof t === "string") : [],
    };
  } catch {
    /* storage unavailable or corrupt — showing the tour again is the safe miss */
    return NO_TOUR;
  }
}

function write(record: TourRecord) {
  try {
    window.localStorage.setItem(TOUR_KEY, JSON.stringify(record));
  } catch {
    /* storage unavailable — the tour still runs correctly for this page */
  }
}

export function markTourDone() {
  write({ ...readTour(), done: true });
}

/** Replaying is a request, so it clears the flag as well as starting the walk. */
export function clearTourDone() {
  write({ ...readTour(), done: false });
}

export function hasSeenTip(id: string): boolean {
  return readTour().tips.includes(id);
}

export function markTipSeen(id: string) {
  const current = readTour();
  if (current.tips.includes(id)) return;
  write({ ...current, tips: [...current.tips, id] });
}
