"use client";

import type { GraphNode } from "@/lib/api";
import type { RouteStop } from "@/lib/graph-layout";
import { tagStyle, tagLabel, stateStyle, stateLabel, STATE_ORDER } from "@/lib/tags";
import { useI18n } from "@/lib/i18n/context";

interface Props {
  stops: RouteStop[];
  currentNodeId: string | null;
  onJump: (node: GraphNode) => void;
  onExpand: () => void;
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

export default function RouteRail({ stops, currentNodeId, onJump, onExpand }: Props) {
  const { t } = useI18n();

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
        {stops.map((stop, i) => {
          const { node } = stop;
          const isCurrent = node.id === currentNodeId;
          const isLast = i === stops.length - 1;

          return (
            <button
              key={node.id}
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

                <span dir="ltr" className="truncate text-start font-mono text-[10.5px] text-graphite">
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
                          {tagLabel(t, tag)}
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
        })}
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
              {stateLabel(t, state)}
            </span>
          );
        })}
      </div>
    </aside>
  );
}
