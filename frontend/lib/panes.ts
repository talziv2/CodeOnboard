import {
  DEFAULT_SOURCE,
  DEFAULT_TUTOR,
  type PaneMode,
  type PanePrefs,
  type Prefs,
} from "@/lib/prefs";

/**
 * Two companion panes, one dock slot.
 *
 * ── THE INVARIANT ─────────────────────────────────────────────────────────────
 *
 *   **At most one pane may be docked and open at a time.** A floating pane is out
 *   of flow and claims no grid track, so any number of them may coexist with a
 *   docked one.
 *
 * That is not a new rule invented for the Tutor — it is the existing grid's rule,
 * written down. `app/session/[id]/page.tsx` reserves a third track only for a pane
 * that is `open && mode === "dock"`, and it can only reserve one. Before this
 * module the constraint was satisfied by there being exactly one pane; now it has
 * to be stated.
 *
 * ── WHY A REDUCER AND NOT TWO `setOpen` CALLS ─────────────────────────────────
 *
 * Because opening one pane is a change to BOTH. "Open the Tutor" means "open the
 * Tutor and, if the Source is holding the column, close it" — and a component
 * that had to remember the second half is a component that will forget it on the
 * third call site. The same reasoning `surfaceTabs.ts` gives for being a reducer
 * over an event union rather than a setter anyone can call.
 *
 * Pure: no React, no storage, no DOM. Every rule below is a test.
 */

export type PaneId = "source" | "tutor";

export const PANE_IDS: PaneId[] = ["source", "tutor"];

const DEFAULTS: Record<PaneId, PanePrefs> = {
  source: DEFAULT_SOURCE,
  tutor: DEFAULT_TUTOR,
};

/** The pane's stored preferences, defaulted for an older blob. */
export function paneOf(prefs: Prefs, id: PaneId): PanePrefs {
  return prefs[id] ?? DEFAULTS[id];
}

function other(id: PaneId): PaneId {
  return id === "source" ? "tutor" : "source";
}

/** Is this pane occupying the third grid track? */
export function isDocked(pane: PanePrefs): boolean {
  return pane.open && pane.mode === "dock";
}

/**
 * Which pane, if any, owns the third grid track.
 *
 * The single question the layout asks. `null` means no column is reserved —
 * either nothing is open, or everything open is floating.
 *
 * `source` wins a tie that cannot happen: the reducer below never leaves both
 * docked, and this returning a deterministic answer if one somehow did is better
 * than the grid reserving a track for a pane that does not render into it.
 */
export function dockedPane(prefs: Prefs): PaneId | null {
  if (isDocked(paneOf(prefs, "source"))) return "source";
  if (isDocked(paneOf(prefs, "tutor"))) return "tutor";
  return null;
}

/** Every pane that should be on screen, docked one first. */
export function openPanes(prefs: Prefs): PaneId[] {
  const docked = dockedPane(prefs);
  const floating = PANE_IDS.filter(
    (id) => id !== docked && paneOf(prefs, id).open
  );
  return docked ? [docked, ...floating] : floating;
}

/**
 * Open `id`.
 *
 * `mustFloat` is `dockWouldCrowd(...)` from the caller — a dock that would leave
 * the reading column under `LESSON_FLOOR` opens floating instead, because a
 * 300px-wide lesson is not a lesson. That is a STARTING POINT, not a lock: the
 * dock control stays live, and the stored mode is what reopens next time.
 *
 * **Opening in `dock` closes the other pane if it is holding the column.** Closing
 * rather than undocking: the evicted pane keeps `mode: "dock"` stored, so
 * reopening it restores what the learner had. Undocking it instead would leave a
 * window on screen they never asked for.
 */
export function openPane(
  prefs: Prefs,
  id: PaneId,
  mustFloat = false
): Partial<Prefs> {
  const pane = paneOf(prefs, id);
  const mode: PaneMode = mustFloat && pane.mode === "dock" ? "float" : pane.mode;
  const patch: Partial<Prefs> = { [id]: { ...pane, open: true, mode } } as Partial<Prefs>;
  if (mode === "dock") {
    const evicted = evict(prefs, id);
    if (evicted) Object.assign(patch, evicted);
  }
  return patch;
}

/**
 * Switch `id` to `mode`.
 *
 * Docking evicts, by the same rule and for the same reason as opening — the
 * learner reached the same state through a different control, and the layout
 * cannot tell the difference. **Floating never evicts anything**, which is what
 * makes Source-docked + Tutor-floating (and the reverse, and both floating)
 * reachable.
 */
export function setPaneMode(
  prefs: Prefs,
  id: PaneId,
  mode: PaneMode
): Partial<Prefs> {
  const pane = paneOf(prefs, id);
  const patch: Partial<Prefs> = { [id]: { ...pane, mode } } as Partial<Prefs>;
  if (mode === "dock" && pane.open) {
    const evicted = evict(prefs, id);
    if (evicted) Object.assign(patch, evicted);
  }
  return patch;
}

/**
 * Close `id`.
 *
 * **Never opens or moves the other pane.** Eviction is not a stack: a learner who
 * opened Chat over Source and then closed Chat asked for one thing to go away,
 * not for another to come back. Restoring it would be the layout second-guessing
 * a decision they just made.
 */
export function closePane(prefs: Prefs, id: PaneId): Partial<Prefs> {
  return { [id]: { ...paneOf(prefs, id), open: false } } as Partial<Prefs>;
}

/** The patch that clears the column for `id`, or null when it is already free. */
function evict(prefs: Prefs, id: PaneId): Partial<Prefs> | null {
  const rival = other(id);
  const pane = paneOf(prefs, rival);
  if (!isDocked(pane)) return null;
  // `open: false` only — `mode` is left alone so reopening restores the learner's
  // own arrangement rather than a state the system chose for them.
  return { [rival]: { ...pane, open: false } } as Partial<Prefs>;
}
