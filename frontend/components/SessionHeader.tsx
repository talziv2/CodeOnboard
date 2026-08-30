"use client";

import DashboardLink from "@/components/DashboardLink";
import SessionMenu from "@/components/SessionMenu";
import SettingsMenu from "@/components/SettingsMenu";
import type { SessionGraph } from "@/lib/api";
import { t } from "@/lib/strings";

/**
 * The session header: four zones, in priority order.
 *
 *   identity │ context ─────────── │ progress │ controls
 *   shrink-0 │ flex-1, floor 15rem │ shrink-0 │ shrink-0
 *
 * IDENTITY also holds the way out — `DashboardLink`, at the leading edge, where
 * a way back belongs and where it cannot be mistaken for one of the trailing
 * controls that change the session. Its label collapses under `sm` so the floor
 * below still holds; see the component for why it is not in the `⋯` menu.
 *
 * The zone that matters is CONTEXT — the repository, the goal, and how deep the
 * learner asked to go. It is what says which session this is and what it is for,
 * and it was the zone being starved: measured at 1280px it rendered at 110px for
 * 84 characters of text, and at 1024px it collapsed to 0 while the header itself
 * overflowed at anything under about 1150px. Nine children competed in one flex
 * row and the controls, which are used rarely, won every time, because `flex-1`
 * with `min-w-0` means "give me what is left" and there was nothing left.
 *
 * The fix is a floor, not a truncation tweak. `min-w-[15rem]` (240px) is a width
 * the goal can no longer be pushed below; four of the seven control widths went
 * behind one 28px `⋯` instead, which is what makes room for it to hold.
 *
 * BOTH progress measures stay, with their two grammars intact — demonstrated is
 * evidence (`7/12`, a fraction the learner can check), stops taken is coverage
 * (`15/15`). Showing only the first reads 0% for someone who walked every stop
 * without answering; showing only the second claims understanding nobody
 * demonstrated. What collapses is their LABELS, not their numbers: the uppercase
 * eyebrows appear on hover or keyboard focus, and the `title` on each number
 * carries the full sentence for anyone who never triggers either.
 */
export default function SessionHeader({
  graph,
  depth,
  pct,
  stopCount,
  scoping,
  scopeNote,
  onScope,
  onBriefing,
  onReplayTour,
  onStartOver,
  startingOver,
  canStartOver,
  onRebuild,
  rebuilding,
  onFinish,
}: {
  graph: SessionGraph;
  depth: string | undefined;
  pct: number;
  stopCount: number;
  scoping: boolean;
  scopeNote: string | null;
  onScope: (direction: "shorter" | "deeper") => void;
  onBriefing: () => void;
  onReplayTour: () => void;
  onStartOver: () => void;
  startingOver: boolean;
  canStartOver: boolean;
  onRebuild: () => void;
  rebuilding: boolean;
  onFinish: () => void;
}) {
  return (
    <header className="flex shrink-0 items-center gap-4 border-b border-rule bg-slab px-5 py-2.5">
      {/* identity, and the way out */}
      <span className="flex shrink-0 items-center gap-3">
        <span className="flex items-center gap-2">
          <span aria-hidden className="h-2 w-2 rotate-45 bg-signal" />
          <span className="font-display text-aside tracking-tight text-chalk">
            {t.appName}
          </span>
        </span>
        <DashboardLink />
      </span>

      {/* context — the zone with a floor */}
      <span className="min-w-[15rem] flex-1 truncate font-mono text-meta text-graphite">
        {graph.repo_url.replace(/^https?:\/\/github\.com\//, "")}
        {graph.goal?.primary_goal && (
          <> &nbsp;·&nbsp; <span className="text-signal">{graph.goal.primary_goal}</span></>
        )}
        {depth && <> &nbsp;·&nbsp; {t.session.depth[depth] ?? depth}</>}
      </span>

      {/* progress — two measures, labels on demand */}
      <span data-tour="progress" className="group flex shrink-0 items-center gap-3">
        <span className="flex items-center gap-2">
          <span className="hidden font-mono text-micro uppercase tracking-[0.13em] text-graphite group-hover:inline group-focus-within:inline">
            {t.session.demonstrated}
          </span>
          <span className="h-1 w-12 overflow-hidden rounded-full bg-raise">
            <span
              className="block h-full rounded-full bg-gradient-to-r from-signal-dim to-signal transition-[width] duration-500"
              style={{ width: `${pct}%` }}
            />
          </span>
          {/* The FRACTION is the number; the percentage is a gloss on it. "47%
              readiness" sounds like a calibrated prediction, where "7 / 15
              required objectives demonstrated" is a claim the learner can check
              against the journey below (M3a.3). */}
          <span
            tabIndex={0}
            className="font-mono text-meta tabular-nums text-chalk"
            title={t.map.coreDemonstrated(
              graph.progress.core_demonstrated,
              graph.progress.core_total
            )}
          >
            {graph.progress.core_demonstrated}/{graph.progress.core_total}
            <span className="text-graphite"> ({pct}%)</span>
          </span>
        </span>

        <span aria-hidden className="text-graphite">
          ·
        </span>

        <span className="flex items-center gap-2">
          <span className="hidden font-mono text-micro uppercase tracking-[0.13em] text-graphite group-hover:inline group-focus-within:inline">
            {t.session.journey}
          </span>
          <span
            tabIndex={0}
            className="font-mono text-meta tabular-nums text-chalk"
            title={t.map.stopsTaken(
              graph.progress.stops_settled,
              graph.progress.stops_total
            )}
          >
            {t.session.journeyCount(
              graph.progress.stops_settled,
              graph.progress.stops_total
            )}
          </span>
        </span>
      </span>

      {/* controls */}
      <span className="flex shrink-0 items-center gap-2">
        <SessionMenu
          stopCount={stopCount}
          scoping={scoping}
          scopeNote={scopeNote}
          onScope={onScope}
          onBriefing={onBriefing}
          onReplayTour={onReplayTour}
          onStartOver={onStartOver}
          startingOver={startingOver}
          canStartOver={canStartOver}
          onRebuild={onRebuild}
          rebuilding={rebuilding}
          onFinish={onFinish}
        />
        <SettingsMenu />
      </span>
    </header>
  );
}
