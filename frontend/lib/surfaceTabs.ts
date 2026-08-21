import type { LessonUi } from "@/lib/flags";

/**
 * What the session column is showing, and the only things that may change it.
 *
 * ── TWO MODES, NOT FOUR PEER TABS ─────────────────────────────────────────────
 *
 * The bar was `Lesson · Understanding · Map`, and the Map did not belong in that
 * list. Lesson and Understanding are two halves of ONE activity — read the stop,
 * then show what you took from it — and both are about the stop the learner is on.
 * The map is not: it is the whole journey, at session altitude, and what it is for
 * is deciding where to go rather than learning anything. A flat bar put a
 * navigation view and a reading view side by side as if choosing between them were
 * the same kind of choice.
 *
 * So there are two modes, and each owns its tabs:
 *
 *   learn  → Lesson · Understanding    this stop: read it, then show what you got
 *   route  → Map · Analysis            the journey: where you are, how it is going
 *
 * `Analysis` is the second half of what the Map tab used to hold. That one view had
 * the route, the two progress measures, the outcome bands, the pattern layer, the
 * breakdowns AND the session log stacked in it — a map you had to scroll past a
 * dashboard to read. The route is navigation; everything else is interpretation of
 * evidence. Splitting them is why the mode exists rather than being a fourth tab.
 *
 * TWO ROWS, one per level: the switch above, the tabs it governs beneath. The switch
 * first sat at the head of the tab row, on the reasoning that one row of chrome could
 * never nest a tab under a tab of the same name (`ui-surfaces.md` §2) — but that risk
 * was about repeating a WORD at two altitudes, and `Learn`/`Lesson` are an activity
 * and a view rather than one name twice. What the single row did cost was the
 * hierarchy: four controls on a line read as four peers, which is the flat bar the
 * modes exist to replace. See `components/lesson/SurfaceTabs.tsx` for the layout.
 *
 * ── R5, and why this is a reducer ──────────────────────────────────────────────
 *
 * The rule: **selection changes only because the learner asked, or because they
 * arrived at a different stop. Never because the phase changed.**
 *
 * Phases and tabs map suspiciously well — STUDY and VERIFY own a question,
 * FEEDBACK and RESOLVED own a verdict, and all four live in Understanding — so
 * "select the tab the phase implies" is a one-line change that would feel helpful
 * and be exactly the surprising navigation this design rules out. Submitting an
 * answer would throw the learner into Understanding; a re-teach would throw them
 * into Lesson mid-sentence.
 *
 * So `TabEvent` has no phase in it, and `reduceTabs` takes no phase, no result, and
 * no lesson. A test can assert that a phase transition left the tab alone; a type
 * can make the transition unable to reach the decision at all. This is the second,
 * which is why the state is a reducer over an explicit event union rather than a
 * setter anyone can call from anywhere.
 *
 * Arrival at a different stop DOES reset to Learn · Lesson, and that is not a phase
 * transition: it is the learner having navigated. Landing on a new stop showing the
 * previous stop's Understanding — its verdict gone, its gaps gone — would be showing
 * them an empty room.
 */
export type SessionMode = "learn" | "route";

export type SessionTab = "lesson" | "understanding" | "map" | "analysis";

/** Modes in switch order. */
export const MODES: SessionMode[] = ["learn", "route"];

const MODE_OF: Record<SessionTab, SessionMode> = {
  lesson: "learn",
  understanding: "learn",
  map: "route",
  analysis: "route",
};

/**
 * Which mode a tab belongs to.
 *
 * A total map over the tab union rather than a lookup that can miss, so adding a tab
 * without deciding its mode is a type error rather than a tab that renders under
 * whichever mode happens to be selected.
 */
export function modeOf(tab: SessionTab): SessionMode {
  return MODE_OF[tab];
}

/** The offered tabs of one mode, in bar order. */
export function tabsInMode(available: SessionTab[], mode: SessionMode): SessionTab[] {
  return available.filter((tab) => modeOf(tab) === mode);
}

/** The modes worth showing a switch for — a mode with no tabs is not a place. */
export function modesIn(available: SessionTab[]): SessionMode[] {
  return MODES.filter((mode) => tabsInMode(available, mode).length > 0);
}

/**
 * The selection: which mode, and the tab remembered inside each.
 *
 * Per-mode memory is the reason the state is a record rather than one tab. Switching
 * to Route to check the map and switching back is "step away and come back", so it
 * has to come back to what was open — a learner who was reading their verdict in
 * Understanding and gets dropped on Lesson has lost their place for having glanced
 * at the map.
 */
export type TabState = {
  readonly mode: SessionMode;
  readonly learn: SessionTab;
  readonly route: SessionTab;
};

export const INITIAL_TABS: TabState = { mode: "learn", learn: "lesson", route: "map" };

/**
 * What may move the selection. Deliberately exhaustive, and deliberately phase-free.
 *
 * Each is a thing the learner did. `arrivedAtStop` is the one that is not a click,
 * and it is still navigation — it fires when `nodeId` changes, which only happens
 * because they advanced, jumped, or were taken to a warm-up they asked for.
 */
export type TabEvent =
  /** Clicked a tab in the bar. */
  | { kind: "picked"; tab: SessionTab }
  /** Clicked the other mode in the switch. */
  | { kind: "switchedMode"; mode: SessionMode }
  /** `nodeId` changed: a different stop is now current. */
  | { kind: "arrivedAtStop" }
  /** Chose a section's overview from the rail — a request to read, so Lesson. */
  | { kind: "openedSection" }
  /** Asked for the whole map. */
  | { kind: "expandedMap" }
  /** Left route mode with Escape. */
  | { kind: "dismissedRoute" };

/**
 * The tabs this build offers, across both modes.
 *
 * `next` keeps the flat two-tab bar it has always had. It is the baseline `surfaces`
 * is measured against (`flags.ts`), and giving it modes would mean two modes of one
 * tab each — a switch that decides nothing, and a difference in the comparison that
 * has nothing to do with the comparison.
 *
 * `sectionOverview` drops `understanding`, because a chapter overview has nothing
 * for it. Understanding is what the learner has SHOWN — a question, an answer, a
 * verdict, open gaps — and all of those are properties of a stop. A chapter has no
 * question and nothing is demonstrated at chapter granularity, so the tab could only
 * ever open onto the previous stop's evidence beside a heading about something else.
 * Route mode is untouched by it: the journey, and the evidence over it, are the same
 * whichever chapter heading is open in the other mode.
 *
 * Dropped rather than disabled: a greyed tab still says "there is something here".
 */
export function tabsFor(
  ui: LessonUi,
  { sectionOverview = false }: { sectionOverview?: boolean } = {}
): SessionTab[] {
  if (ui !== "surfaces") return ["lesson", "map"];
  return sectionOverview
    ? ["lesson", "map", "analysis"]
    : ["lesson", "understanding", "map", "analysis"];
}

/**
 * The tab actually rendered: the remembered one, while the bar still offers it.
 *
 * Derived rather than corrected in an effect. The offered tabs can shrink underneath
 * the state — opening a chapter overview drops Understanding — and an effect that
 * fixed the state up afterwards would be a second thing that moves the selection,
 * which is exactly what R5's reducer exists to prevent.
 */
export function activeTab(state: TabState, available: SessionTab[]): SessionTab {
  const inMode = tabsInMode(available, state.mode);
  const remembered = state[state.mode];
  if (inMode.includes(remembered)) return remembered;
  return inMode[0] ?? available[0] ?? "lesson";
}

/** Select `tab`, entering its mode and remembering it there. */
function land(state: TabState, tab: SessionTab): TabState {
  const mode = modeOf(tab);
  return mode === "learn"
    ? { mode, learn: tab, route: state.route }
    : { mode, learn: state.learn, route: tab };
}

/** Back to learn mode, on its first offered tab — Lesson wherever it exists. */
function toLearn(state: TabState, available: SessionTab[]): TabState {
  const first = tabsInMode(available, "learn")[0];
  return first ? land(state, first) : state;
}

/**
 * The next selection, given the current one and something the learner did.
 *
 * `available` is passed rather than derived so the reducer cannot land on a tab the
 * build does not render — `understanding` does not exist under `next`, and a stale
 * event naming it must be ignored rather than blanking the column.
 */
export function reduceTabs(
  state: TabState,
  event: TabEvent,
  available: SessionTab[]
): TabState {
  switch (event.kind) {
    case "picked":
      return available.includes(event.tab) ? land(state, event.tab) : state;

    // The mode's own remembered tab comes back with it — the switch changes what the
    // learner is doing, not where they had got to inside it.
    case "switchedMode":
      return tabsInMode(available, event.mode).length === 0
        ? state
        : { ...state, mode: event.mode };

    // A different stop. Back to the lesson: the learner has moved, and the previous
    // stop's Understanding does not describe this one.
    case "arrivedAtStop":
      return toLearn(state, available);

    // A request to READ something, which is Lesson's purpose.
    case "openedSection":
      return toLearn(state, available);

    case "expandedMap":
      return available.includes("map") ? land(state, "map") : state;

    // Escape is scoped to route mode. From anywhere else it means nothing here, and
    // must not be allowed to mean "go to Lesson" — that would make Escape a way to
    // lose your place while answering. Returning keeps whichever learn tab was open,
    // because leaving the map is going back, not starting over.
    case "dismissedRoute":
      return state.mode === "route" ? { ...state, mode: "learn" } : state;
  }
}

/**
 * Which surface a tab shows, for the tabs that show one.
 *
 * Route mode's tabs are not surfaces — they are peer views of the session — so this
 * is partial by design rather than by omission.
 */
export function surfaceForTab(tab: SessionTab): "lesson" | "understanding" | null {
  return modeOf(tab) === "learn" ? (tab as "lesson" | "understanding") : null;
}
