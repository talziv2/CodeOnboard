"use client";

import type { SessionMode, SessionTab } from "@/lib/surfaceTabs";
import { modeOf, modesIn, tabsInMode } from "@/lib/surfaceTabs";
import { isSplitSurfaces, lessonUi } from "@/lib/flags";
import { t } from "@/lib/strings";

/**
 * The session column's chrome: what you are doing, and then which view of it.
 *
 *   ┌ [Learn|Route]                              …hint · Show source ┐   mode
 *   └ Lesson · Understanding                                         ┘   view
 *
 * TWO ROWS, one per level. The switch chooses the ACTIVITY — study this stop, or
 * navigate the journey — and the tabs choose the view within that activity. Before
 * this the bar was flat, `Lesson · Understanding · Map`, which offered a navigation
 * view and a reading view as if picking between them were the same kind of decision;
 * the reasoning for the modes is in `lib/surfaceTabs.ts`.
 *
 * The two levels first shipped side by side in one row, and side by side is what
 * hid the hierarchy: four controls on one line read as four peers with an odd gap in
 * them, which is the arrangement the modes exist to replace. Stacked, the geometry
 * states the containment — the switch is above, the tabs it governs are beneath —
 * and the ambiguity a second bar was supposed to cause (a tab called Lesson under a
 * mode called Learn) does not arise, because `Learn` names an activity and `Lesson`
 * names a view; they are not the same word at two altitudes.
 *
 * The right-hand group rides the MODE row rather than the tab row. Everything in it
 * — the map hint, `Show source`, `Show route` — is session chrome rather than a
 * choice between views, and keeping the tab row to nothing but tabs is what makes
 * the second level legible at a glance.
 *
 * `next` gets ONE row, unchanged: no modes, so no upper level to draw, and it stays
 * live as the thing `surfaces` is measured against (`tabsFor`). This component cannot
 * change the selection — it can only report that something was clicked, which is most
 * of what makes R5 enforceable.
 *
 * ── The dot ───────────────────────────────────────────────────────────────────
 *
 * A tab may carry a dot meaning **something changed here while you were looking
 * elsewhere**. It is the first of §5's three deliberately redundant signals for R1,
 * and it belongs to the bar rather than to either surface: it is the only thing on
 * screen in both, and a change announced only inside the surface that changed is
 * announced to nobody.
 *
 * A dot on a tab of the OTHER mode has nowhere to land — that tab is not rendered —
 * so it escalates to the mode button. Without that, the map's route mark and any
 * change in Understanding would go silent for exactly as long as the learner was in
 * the other mode, which is the whole time the signal is for.
 *
 * It is a dot rather than a count. A count invites the learner to reconcile it —
 * "three things changed, have I seen three?" — and the changes are not countable in
 * any way they would trust; the brief's counters already carry the numbers that are
 * real. What the dot has to convey is one bit: worth a look.
 *
 * Cleared by visiting the tab, never by a timer.
 */
export default function SurfaceTabs({
  tabs,
  active,
  changed,
  onPick,
  onSwitchMode,
  trailing,
}: {
  /** Every tab this build offers, across both modes. */
  tabs: SessionTab[];
  active: SessionTab;
  /** Tabs with an unseen change. */
  changed?: SessionTab[];
  onPick: (tab: SessionTab) => void;
  onSwitchMode: (mode: SessionMode) => void;
  /** The bar's right-hand group — the map hint, `Show source`. */
  trailing?: React.ReactNode;
}) {
  // The map's label depends on the BUILD, not on how many tabs happen to be up.
  // `Progress map` is what the two-tab bar has always said and `next` has to keep
  // saying it — it stays live as the thing `surfaces` is measured against, so a
  // relabel there would be a difference in the comparison that has nothing to do
  // with the comparison. In `surfaces` the qualifier is the longest word on the bar
  // and earns nothing.
  const modal = isSplitSurfaces(lessonUi());
  const label = (tab: SessionTab) =>
    tab === "map" && !modal ? t.session.tabMap : t.session.tab[tab];

  const mode = modeOf(active);
  const modes = modal ? modesIn(tabs) : [];
  // In a mode, only that mode's tabs. Under `next` there are no modes, so the bar is
  // the flat list it was.
  const shown = modal ? tabsInMode(tabs, mode) : tabs;
  const hasChange = (tab: SessionTab) => tab !== active && (changed?.includes(tab) ?? false);

  return (
    <>
      {/* ── LEVEL ONE: what you are doing ────────────────────────────────────
          Drawn only when there is more than one mode to choose between, which
          means never under `next`. A row containing one inert control would be a
          level that decides nothing, and the trailing group has to stay reachable
          in that build — so it falls through to the tab row below. */}
      {modes.length > 1 && (
        <div className="flex shrink-0 items-center gap-3 border-b border-rule bg-slab px-5 py-2">
          <div
            role="group"
            aria-label={t.session.modeLabel}
            // `bg-ink` inside a `bg-slab` row: the pill was a raised chip on the
            // page ground, and on its own bar the ground moved up under it. Same
            // colours, opposite roles — without the swap the container's edges
            // vanish and the two segments read as loose words.
            className="flex items-center gap-0.5 rounded-chip border border-rule bg-ink p-0.5"
          >
            {modes.map((m) => {
              const isHere = m === mode;
              return (
                <button
                  key={m}
                  data-tour={`mode-${m}`}
                  onClick={() => onSwitchMode(m)}
                  // `aria-pressed` rather than `aria-current`: this is a toggle
                  // between two states of the same column, not a link to a page.
                  // `aria-current` is the tabs' own claim on the row below, and
                  // having both say it would leave a screen reader with two
                  // "current" things in one piece of chrome.
                  aria-pressed={isHere}
                  // `signal-wash` + `signal`, which is the map's own current-stop
                  // treatment: signal is reserved for "you are here" and the active
                  // mode is exactly that, so the chrome says it in the vocabulary
                  // the rest of the app already uses.
                  //
                  // Was `bg-raise text-chalk`. `raise` is a progress-track fill and
                  // `globals.css` says no control is ever drawn on it — which is why
                  // its contrast is measured against nothing a button needs, and why
                  // the active chip went flat in the light palette.
                  className={`flex items-center gap-1.5 rounded-chip px-3 py-1 font-mono text-micro uppercase tracking-[0.13em] transition ${
                    isHere ? "bg-signal-wash text-signal" : "text-graphite hover:text-chalk"
                  }`}
                >
                  {t.session.mode[m]}
                  {/* Escalated from a tab that is not on screen in this mode. */}
                  {!isHere && tabsInMode(tabs, m).some(hasChange) && (
                    <span aria-hidden className="size-1.5 rounded-full bg-rust" />
                  )}
                </button>
              );
            })}
          </div>

          {trailing && <span className="ms-auto flex items-center gap-3">{trailing}</span>}
        </div>
      )}

      {/* ── LEVEL TWO: which view of it ──────────────────────────────────────
          Nothing but tabs, when there is a mode row above to carry the rest. */}
      <div className="flex shrink-0 items-center gap-1 border-b border-rule px-5">
        {shown.map((tab) => {
          const isActive = tab === active;
          // A dot on the tab you are already looking at would be reporting a change
          // to the person watching it happen.
          return (
            <button
              key={tab}
              data-tour={tab === "understanding" ? "tab-understanding" : undefined}
              onClick={() => onPick(tab)}
              aria-current={isActive ? "page" : undefined}
              className={`-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2.5 font-mono text-micro uppercase tracking-[0.13em] transition ${
                isActive
                  ? "border-signal text-signal"
                  : "border-transparent text-graphite hover:text-chalk"
              }`}
            >
              {label(tab)}
              {hasChange(tab) && <span aria-hidden className="size-1.5 rounded-full bg-rust" />}
            </button>
          );
        })}

        {/* The dot's meaning, for anyone not seeing it — and deliberately OUTSIDE the
            buttons.
            Inside, the text became part of each tab's accessible name ("Lesson Lesson
            has changed since you last looked"), which is both a worse name and only
            reaches someone who has already focused the tab. A polite live region
            announces it at the moment it appears instead, which is what R1 actually
            asks for: told where you are, about something you cannot see. Named per tab,
            because "something changed" without saying where is worse than silence —
            and named by TAB even when the dot is drawn on a mode button, since the tab
            is the thing the learner has to go to. */}
        <span aria-live="polite" className="sr-only">
          {tabs
            .filter(hasChange)
            .map((tab) => t.session.tabChanged(label(tab)))
            .join(" ")}
        </span>

        {/* `next` has no mode row, so the trailing group lands here instead — the
            one build where these two levels are still one. */}
        {modes.length <= 1 && trailing && (
          <span className="ms-auto flex items-center gap-3">{trailing}</span>
        )}
      </div>
    </>
  );
}
