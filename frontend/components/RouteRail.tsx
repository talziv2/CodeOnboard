"use client";

import { useState } from "react";
import type { Area, GraphNode } from "@/lib/api";
import type { RouteStop } from "@/lib/graph-layout";
import { tagStyle, tagLabel, stateStyle, stateLabel, STATE_ORDER } from "@/lib/tags";
import { t } from "@/lib/strings";

interface Props {
  stops: RouteStop[];
  currentNodeId: string | null;
  /** Empty on pre-B3 graphs, which then render as one ungrouped list. */
  areas?: Area[];
  onJump: (node: GraphNode) => void;
  onExpand: () => void;
}

/** One area's heading plus the stops under it. */
interface RailGroup {
  area: Area | null;
  stops: RouteStop[];
}

/**
 * Split the route into area groups, preserving WALK ORDER within each.
 *
 * Grouping is a rendering concern only: the stops keep the order `buildRoute`
 * produced, and no traversal changes. A stop whose `area_id` names no declared
 * area, or which has none at all, falls into a trailing ungrouped bucket rather
 * than being hidden — a graph the planner never grouped must still render whole.
 */
function groupByArea(stops: RouteStop[], areas: Area[]): RailGroup[] {
  if (areas.length === 0) return [{ area: null, stops }];

  const groups = new Map<string, RailGroup>();
  for (const area of areas) groups.set(area.id, { area, stops: [] });
  const ungrouped: RouteStop[] = [];

  for (const stop of stops) {
    const id = stop.node.area_id;
    const group = id ? groups.get(id) : undefined;
    if (group) group.stops.push(stop);
    else ungrouped.push(stop);
  }

  const ordered = [...groups.values()].filter((g) => g.stops.length > 0);
  if (ungrouped.length > 0) ordered.push({ area: null, stops: ungrouped });
  return ordered;
}

/** Pin shape encodes state so the rail stays readable without colour. */
function Pin({ node, isCurrent }: { node: GraphNode; isCurrent: boolean }) {
  const style = stateStyle(node.understanding_state);
  return (
    <span
      aria-hidden
      className="relative z-10 mt-0.5 block h-[17px] w-[17px] shrink-0 rounded-full border-[1.5px] bg-ink"
      style={{
        borderColor: isCurrent ? "var(--color-signal)" : style.stroke,
        background: isCurrent ? "var(--color-ink)" : style.fill,
        boxShadow: isCurrent ? "0 0 0 3px rgba(91,200,232,0.16)" : undefined,
      }}
    >
      {isCurrent && (
        <span className="absolute inset-[3.5px] rounded-full bg-signal" />
      )}
    </span>
  );
}

/** One stop in the rail. */
function Stop({
  stop, isCurrent, isLast, onJump,
}: {
  stop: RouteStop;
  isCurrent: boolean;
  isLast: boolean;
  onJump: (node: GraphNode) => void;
}) {
  const { node } = stop;
  return (
    <button
      onClick={() => onJump(node)}
      aria-current={isCurrent ? "step" : undefined}
      className={`group relative grid w-full grid-cols-[18px_1fr] gap-3 py-1.5 text-start ${
        stop.isPrerequisite ? "ms-[22px] w-[calc(100%-22px)]" : ""
      }`}
    >
      {/* connector down to the next stop */}
      {!isLast && (
        <span
          aria-hidden
          className="absolute start-2 top-[22px] bottom-[-8px] w-px bg-rule"
        />
      )}

      <Pin node={node} isCurrent={isCurrent} />

      <span className="flex min-w-0 flex-col gap-[3px]">
        {stop.isPrerequisite && (
          <span className="flex items-center gap-[5px] font-mono text-[9.5px] tracking-[0.06em] text-signal">
            <span aria-hidden className="h-px w-3 bg-signal" />
            {t.rail.addedAfterConfusion}
          </span>
        )}

        <span
          className={`text-[12.5px] leading-[1.35] transition ${
            isCurrent
              ? "font-semibold text-signal"
              : "font-medium text-chalk group-hover:text-signal"
          }`}
        >
          {node.title}
        </span>

        <span className="truncate text-start font-mono text-[10.5px] text-graphite">
          {node.file}
        </span>

        {node.concept_tags.length > 0 && (
          <span className="mt-0.5 flex flex-wrap gap-1">
            {node.concept_tags.slice(0, 3).map((tag) => {
              const s = tagStyle(tag);
              return (
                <span
                  key={tag}
                  className="rounded-[2px] border px-[5px] py-px font-mono text-[9.5px] tracking-[0.05em]"
                  style={{ color: s.text, borderColor: s.border, background: s.background }}
                >
                  {tagLabel(tag)}
                </span>
              );
            })}
          </span>
        )}

        {node.weak_spot && (
          <span className="font-mono text-[9.5px] tracking-[0.05em] text-rust">
            {t.rail.markedWeak}
          </span>
        )}
      </span>
    </button>
  );
}

export default function RouteRail({
  stops, currentNodeId, areas, onJump, onExpand,
}: Props) {
  const [showOptional, setShowOptional] = useState(false);

  // Optional units are depth the learner did not ask for. Collapsing them keeps
  // a long journey legible; they stay one click away, and never disappear.
  const optional = stops.filter((s) => s.node.priority === "optional");
  const spine = optional.length > 0
    ? stops.filter((s) => s.node.priority !== "optional")
    : stops;
  const groups = groupByArea(spine, areas ?? []);

  // The current node must never be hidden behind a collapsed section.
  const currentIsOptional = optional.some((s) => s.node.id === currentNodeId);
  const optionalOpen = showOptional || currentIsOptional;

  return (
    <aside className="flex h-full min-h-0 flex-col gap-3 border-e border-rule bg-trench py-4">
      <div className="flex items-baseline justify-between px-4">
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
          {t.rail.title}
        </span>
        <button
          onClick={onExpand}
          className="font-mono text-[10.5px] text-signal transition hover:text-chalk"
        >
          {t.rail.openMap}
        </button>
      </div>

      <nav className="min-h-0 flex-1 overflow-y-auto px-4">
        {groups.map((group, gi) => (
          <div key={group.area?.id ?? `ungrouped-${gi}`}>
            {group.area && (
              <div className="mb-1 mt-3 flex flex-col gap-0.5 first:mt-0">
                <span className="font-mono text-[9.5px] uppercase tracking-[0.15em] text-signal-dim">
                  {group.area.title}
                </span>
                {group.area.why && (
                  <span className="text-[10.5px] leading-snug text-graphite">
                    {group.area.why}
                  </span>
                )}
              </div>
            )}
            {group.stops.map((stop, i) => (
              <Stop
                key={stop.node.id}
                stop={stop}
                isCurrent={stop.node.id === currentNodeId}
                // The connector joins stops WITHIN a group; an area heading is
                // a break in the line, not something to draw through.
                isLast={i === group.stops.length - 1}
                onJump={onJump}
              />
            ))}
          </div>
        ))}

        {optional.length > 0 && (
          <div className="mt-3 border-t border-rule pt-2">
            <button
              onClick={() => setShowOptional((v) => !v)}
              disabled={currentIsOptional}
              className="flex w-full items-center gap-2 py-1 font-mono text-[10px] uppercase tracking-[0.13em] text-graphite transition hover:text-signal disabled:opacity-60"
            >
              <span aria-hidden className={optionalOpen ? "rotate-90" : ""}>
                ›
              </span>
              {optionalOpen && !currentIsOptional
                ? t.rail.hideOptional
                : t.rail.optionalStops(optional.length)}
            </button>
            {optionalOpen &&
              optional.map((stop, i) => (
                <Stop
                  key={stop.node.id}
                  stop={stop}
                  isCurrent={stop.node.id === currentNodeId}
                  isLast={i === optional.length - 1}
                  onJump={onJump}
                />
              ))}
          </div>
        )}
      </nav>

      <div className="flex shrink-0 flex-col gap-[7px] border-t border-rule px-4 pt-3">
        {STATE_ORDER.map((state) => {
          const s = stateStyle(state);
          return (
            <span
              key={state}
              className="flex items-center gap-[7px] font-mono text-[10.5px] text-graphite"
            >
              <span
                aria-hidden
                className="h-[9px] w-[9px] shrink-0 rounded-full border-[1.5px]"
                style={{ borderColor: s.stroke, background: s.fill }}
              />
              {stateLabel(state)}
            </span>
          );
        })}
      </div>
    </aside>
  );
}
