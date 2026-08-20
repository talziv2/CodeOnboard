import type { LessonUi } from "@/lib/flags";

/**
 * Which tab the session column is showing, and the only things that may change it.
 *
 * ONE BAR, NOT TWO. The column already had `Lesson · Progress map`. Adding
 * `Lesson · Understanding` inside it would produce two bars, one containing a tab
 * called `Lesson` nested under a tab called `Lesson` — not a styling problem but an
 * ambiguity. The map is already a peer view of the session rather than a child of
 * the lesson, so merging to `Lesson · Understanding · Map` is more honest than the
 * nesting it replaces as well as unambiguous (`ui-surfaces.md` §2).
 *
 * ── R5, and why this is a reducer ──────────────────────────────────────────────
 *
 * The rule: **tab selection changes only because the learner asked, or because they
 * arrived at a different stop. Never because the phase changed.**
 *
 * Phases and tabs map suspiciously well — STUDY and VERIFY own a question,
 * FEEDBACK and RESOLVED own a verdict, and all four live in Understanding — so
 * "select the tab the phase implies" is a one-line change that would feel helpful
 * and be exactly the surprising navigation this design rules out. Submitting an
 * answer would throw the learner into Understanding; a re-teach would throw them
 * into Lesson mid-sentence.
 *
 * So `TabEvent` has no phase in it, and `nextTab` takes no phase, no result, and no
 * lesson. A test can assert that a phase transition left the tab alone; a type can
 * make the transition unable to reach the decision at all. This is the second,
 * which is why the tab state is a reducer over an explicit event union rather than
 * a `setTab` anyone can call from anywhere — the old shape, where four call sites
 * each decided for themselves, is one careless `useEffect` away from breaking R5
 * with nothing to catch it.
 *
 * Arrival at a different stop DOES reset to Lesson, and that is not a phase
 * transition: it is the learner having navigated. Landing on a new stop showing the
 * previous stop's Understanding — its verdict gone, its gaps gone — would be
 * showing them an empty room.
 */
export type SessionTab = "lesson" | "understanding" | "map";

/**
 * What may move the tab. Deliberately exhaustive, and deliberately phase-free.
 *
 * Each is a thing the learner did. `arrivedAtStop` is the one that is not a click
 * on a tab, and it is still navigation — it fires when `nodeId` changes, which only
 * happens because they advanced, jumped, or were taken to a warm-up they asked for.
 */
export type TabEvent =
  /** Clicked a tab in the bar. */
  | { kind: "picked"; tab: SessionTab }
  /** `nodeId` changed: a different stop is now current. */
  | { kind: "arrivedAtStop" }
  /** Chose a section's overview from the rail — a request to read, so Lesson. */
  | { kind: "openedSection" }
  /** Asked for the whole map. */
  | { kind: "expandedMap" }
  /** Left the map with Escape. */
  | { kind: "dismissedMap" };

/**
 * The tabs this build offers, in bar order.
 *
 * `sectionOverview` drops `understanding`, because a chapter overview has nothing
 * for it. Understanding is what the learner has SHOWN — a question, an answer, a
 * verdict, open gaps — and all of those are properties of a stop. A chapter has no
 * question and nothing is demonstrated at chapter granularity, so the tab could only
 * ever open onto the previous stop's evidence beside a heading about something else,
 * or onto nothing at all. Offering it is the bar claiming a view that does not exist.
 *
 * Dropped rather than disabled: a greyed tab still says "there is something here".
 */
export function tabsFor(
  ui: LessonUi,
  { sectionOverview = false }: { sectionOverview?: boolean } = {}
): SessionTab[] {
  if (ui !== "surfaces") return ["lesson", "map"];
  return sectionOverview ? ["lesson", "map"] : ["lesson", "understanding", "map"];
}

/**
 * The next tab, given the current one and something the learner did.
 *
 * `available` is passed rather than derived so the reducer cannot land on a tab the
 * build does not render — the `understanding` tab does not exist under `next`, and
 * a stale event naming it must be ignored rather than blanking the column.
 */
export function nextTab(
  current: SessionTab,
  event: TabEvent,
  available: SessionTab[]
): SessionTab {
  const has = (tab: SessionTab) => available.includes(tab);
  const fallback = has("lesson") ? "lesson" : available[0];

  switch (event.kind) {
    case "picked":
      return has(event.tab) ? event.tab : current;

    // A different stop. Reset to Lesson: the learner has moved, and the previous
    // stop's Understanding does not describe this one.
    case "arrivedAtStop":
      return fallback;

    // Both are requests to READ something, which is Lesson's purpose.
    case "openedSection":
      return fallback;

    case "expandedMap":
      return has("map") ? "map" : current;

    // Escape is scoped to the map. From anywhere else it means nothing here, and
    // must not be allowed to mean "go to Lesson" — that would make Escape a way to
    // lose your place while answering.
    case "dismissedMap":
      return current === "map" ? fallback : current;
  }
}

/**
 * Which surface a tab shows, for the tabs that show one.
 *
 * `map` is not a surface — it is a peer view of the session — so this is partial by
 * design rather than by omission.
 */
export function surfaceForTab(tab: SessionTab): "lesson" | "understanding" | null {
  return tab === "map" ? null : tab;
}
