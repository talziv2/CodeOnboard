"use client";

import type { SessionTab } from "@/lib/surfaceTabs";
import { t } from "@/lib/strings";

/**
 * The session column's one tab bar.
 *
 * Renders whatever tabs the build offers, so it is the same component under `next`
 * (`Lesson · Progress map`) and `surfaces` (`Lesson · Understanding · Map`). The bar
 * did not previously exist as a component — it was inline in the session page, with
 * `setTab` called from four places — and extracting it is most of what makes R5
 * enforceable: this component cannot change the tab, it can only report that a tab
 * was clicked.
 *
 * ── The dot ───────────────────────────────────────────────────────────────────
 *
 * A tab may carry a dot meaning **something changed here while you were looking
 * elsewhere**. It is the first of §5's three deliberately redundant signals for R1,
 * and it belongs to the bar rather than to either surface: it is the only thing on
 * screen in both, and a change announced only inside the surface that changed is
 * announced to nobody.
 *
 * It is a dot rather than a count. A count invites the learner to reconcile it —
 * "three things changed, have I seen three?" — and the changes are not countable in
 * any way they would trust; the brief's counters already carry the numbers that are
 * real. What the dot has to convey is one bit: worth a look.
 *
 * Cleared by visiting the tab, never by a timer. `unattendedChange` is owned by the
 * session page, and the wiring to real adaptation signals is S4; the bar takes it as
 * a prop now so the mechanism is testable before anything drives it.
 */
export default function SurfaceTabs({
  tabs,
  active,
  changed,
  onPick,
  trailing,
}: {
  tabs: SessionTab[];
  active: SessionTab;
  /** Tabs with an unseen change. */
  changed?: SessionTab[];
  onPick: (tab: SessionTab) => void;
  /** The bar's right-hand group — the map hint, `Show source`. */
  trailing?: React.ReactNode;
}) {
  // The map's label depends on how many tabs there are. `Progress map` is what the
  // two-tab bar has always said and `next` has to keep saying it — it stays live as
  // the thing `surfaces` is measured against, so a relabel there would be a
  // difference in the comparison that has nothing to do with the comparison. In a
  // three-tab bar the qualifier is the longest word on the bar and earns nothing.
  const label = (tab: SessionTab) =>
    tab === "map" && tabs.length === 2 ? t.session.tabMap : t.session.tab[tab];

  return (
    <div className="flex shrink-0 items-center gap-1 border-b border-rule px-5">
      {tabs.map((tab) => {
        const isActive = tab === active;
        // A dot on the tab you are already looking at would be reporting a change
        // to the person watching it happen.
        const hasDot = !isActive && (changed?.includes(tab) ?? false);
        return (
          <button
            key={tab}
            onClick={() => onPick(tab)}
            aria-current={isActive ? "page" : undefined}
            className={`-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2.5 font-mono text-micro uppercase tracking-[0.13em] transition ${
              isActive
                ? "border-signal text-signal"
                : "border-transparent text-graphite hover:text-chalk"
            }`}
          >
            {label(tab)}
            {hasDot && <span aria-hidden className="size-1.5 rounded-full bg-rust" />}
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
          because "something changed" without saying where is worse than silence. */}
      <span aria-live="polite" className="sr-only">
        {tabs
          .filter((tab) => tab !== active && (changed?.includes(tab) ?? false))
          .map((tab) => t.session.tabChanged(label(tab)))
          .join(" ")}
      </span>

      {trailing && <span className="ms-auto flex items-center gap-3">{trailing}</span>}
    </div>
  );
}
