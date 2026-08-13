"use client";

import { useMemo } from "react";
import type { GraphNode, GraphEdge, UnderstandingState } from "@/lib/api";
import { buildRoute } from "@/lib/graph-layout";
import {
  tagStyle, tagLabel, stateStyle, stateLabel, isCanonicalTag, STATE_ORDER,
} from "@/lib/tags";
import { t } from "@/lib/strings";

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  currentNodeId: string | null;
  readiness: number;
  repoUrl?: string;
  onNodeClick: (node: GraphNode) => void;
}

type Tally = Record<UnderstandingState, number>;

const emptyTally = (): Tally => ({
  understood: 0,
  partial: 0,
  failed: 0,
  not_started: 0,
});

/** Proportional bar of the state mix. Carries the aggregate at a glance
 *  without asking anyone to read four numbers. */
function StateStrip({ tally, total }: { tally: Tally; total: number }) {
  return (
    <span className="flex h-1.5 w-full overflow-hidden rounded-full bg-raise">
      {STATE_ORDER.map((state) => {
        const n = tally[state];
        if (n === 0) return null;
        return (
          <span
            key={state}
            title={`${n} ${stateLabel(state)}`}
            style={{
              width: `${(n / total) * 100}%`,
              background: state === "not_started" ? "var(--color-rule)" : stateStyle(state).stroke,
            }}
          />
        );
      })}
    </span>
  );
}

/** One row of the "by concept" / "by file" breakdowns. */
function BreakdownRow({
  label, sublabel, tally, total, accent,
}: {
  label: React.ReactNode;
  sublabel?: string;
  tally: Tally;
  total: number;
  accent?: string;
}) {
  return (
    <li className="flex flex-col gap-1.5">
      <span className="flex items-baseline justify-between gap-3">
        <span className="min-w-0 truncate" style={accent ? { color: accent } : undefined}>
          {label}
        </span>
        <span className="shrink-0 font-mono text-[10.5px] tabular-nums text-graphite">
          {sublabel ?? `${tally.understood}/${total}`}
        </span>
      </span>
      <StateStrip tally={tally} total={total} />
    </li>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3.5 rounded-md border border-rule bg-slab p-4">
      <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">{title}</h3>
      {children}
    </section>
  );
}

export default function MapView({
  nodes, edges, currentNodeId, readiness, repoUrl, onNodeClick,
}: Props) {
  const stops = useMemo(() => buildRoute(nodes, edges), [nodes, edges]);

  const summary = useMemo(() => {
    const overall = emptyTally();
    const byTag = new Map<string, Tally>();
    const byFile = new Map<string, Tally>();

    for (const node of nodes) {
      const state = node.understanding_state;
      overall[state] = (overall[state] ?? 0) + 1;

      for (const tag of node.concept_tags) {
        const tally = byTag.get(tag) ?? emptyTally();
        tally[state] += 1;
        byTag.set(tag, tally);
      }

      const f = byFile.get(node.file) ?? emptyTally();
      f[state] += 1;
      byFile.set(node.file, f);
    }

    const totalOf = (tally: Tally) => STATE_ORDER.reduce((sum, s) => sum + tally[s], 0);
    const rank = (a: [string, Tally], b: [string, Tally]) =>
      totalOf(b[1]) - totalOf(a[1]) || a[0].localeCompare(b[0]);

    const entries = [...byTag.entries()];
    return {
      overall,
      // The canonical vocabulary answers "what kind of understanding"; free-form
      // tags answer "on what topic". Mixing them buries the six that matter.
      kinds: entries
        .filter(([tag]) => isCanonicalTag(tag))
        .sort(rank)
        .map(([k, tally]) => [k, tally, totalOf(tally)] as const),
      topics: entries
        .filter(([tag]) => !isCanonicalTag(tag))
        .sort(rank)
        .map(([k, tally]) => [k, tally, totalOf(tally)] as const),
      files: [...byFile.entries()].sort(rank).map(([k, tally]) => [k, tally, totalOf(tally)] as const),
      weak: nodes.filter((n) => n.weak_spot).length,
    };
  }, [nodes]);

  const pct = Math.round(readiness * 100);
  const repo = repoUrl?.replace(/^https?:\/\/github\.com\//, "").replace(/\.git$/, "");

  return (
    <div className="h-full overflow-y-auto px-6 py-7">
      <div className="mx-auto flex max-w-4xl flex-col gap-7">

        {/* headline */}
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
              {t.map.label}
            </span>
            <h2 className="font-display text-[25px] font-medium leading-tight tracking-tight text-chalk">
              {repo ?? t.map.thisCodebase}
            </h2>
            <p className="text-[12.5px] text-graphite">
              {t.map.conceptsUnderstood(summary.overall.understood, nodes.length)}
              {" · "}
              {t.map.filesTouched(summary.files.length)}
              {summary.weak > 0 && (
                <> · <span className="text-rust">{t.map.markedWeak(summary.weak)}</span></>
              )}
            </p>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-display text-[34px] leading-none tabular-nums text-signal">
              {pct}%
            </span>
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-graphite">
              {t.map.readiness}
            </span>
          </div>
        </header>

        {/* overall state mix */}
        <div className="flex flex-col gap-2.5">
          <StateStrip tally={summary.overall} total={Math.max(nodes.length, 1)} />
          <div className="flex flex-wrap gap-x-5 gap-y-1.5">
            {STATE_ORDER.map((state) => (
              <span
                key={state}
                className="flex items-center gap-2 font-mono text-[10.5px] text-graphite"
              >
                <span
                  aria-hidden
                  className="h-[9px] w-[9px] shrink-0 rounded-full border-[1.5px]"
                  style={{ borderColor: stateStyle(state).stroke, background: stateStyle(state).fill }}
                />
                <span className="tabular-nums text-chalk">{summary.overall[state]}</span>
                {stateLabel(state)}
              </span>
            ))}
          </div>
        </div>

        {/* the two breakdowns that make this a reflection view rather than a list */}
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title={t.map.byKind}>
            <ul className="flex flex-col gap-3">
              {summary.kinds.map(([tag, tally, total]) => (
                <BreakdownRow
                  key={tag}
                  label={<span className="font-mono text-[11px]">{tagLabel(tag)}</span>}
                  accent={tagStyle(tag).text}
                  tally={tally}
                  total={total}
                />
              ))}
            </ul>

            {summary.topics.length > 0 && (
              <div className="flex flex-col gap-2 border-t border-rule pt-3">
                <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-graphite">
                  {t.map.topicsTouched}
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {summary.topics.map(([tag, tally, total]) => (
                    <span
                      key={tag}
                      title={t.map.understoodOfTotal(tally.understood, total)}
                      className="rounded-[2px] border border-rule px-1.5 py-px font-mono text-[9.5px] tracking-[0.05em] text-graphite"
                    >
                      {tagLabel(tag)}
                      {total > 1 && <span className="text-paper"> ×{total}</span>}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </Panel>

          <Panel title={t.map.whereInRepo}>
            <ul className="flex flex-col gap-3">
              {summary.files.map(([file, tally, total]) => (
                <BreakdownRow
                  key={file}
                  label={
                    <span className="block truncate text-start font-mono text-[11px] text-paper">
                      {file}
                    </span>
                  }
                  sublabel={`${tally.understood}/${total}`}
                  tally={tally}
                  total={total}
                />
              ))}
            </ul>
          </Panel>
        </div>

        {/* the route itself */}
        <section className="flex flex-col gap-4">
          <h3 className="flex items-center gap-2.5 font-mono text-[10px] uppercase tracking-[0.16em] text-graphite">
            {t.map.theRoute}
            <span aria-hidden className="h-px flex-1 bg-rule" />
          </h3>

          <ol className="flex flex-col">
            {stops.map((stop, i) => {
              const { node } = stop;
              const isCurrent = node.id === currentNodeId;
              const s = stateStyle(node.understanding_state);
              const isLast = i === stops.length - 1;
              // A prerequisite connects to the node it unlocks, so the segment
              // below it is the adaptive one.
              const nextIsUnlock = stop.isPrerequisite;

              return (
                <li
                  key={node.id}
                  className={`relative grid grid-cols-[34px_1fr] gap-4 pb-5 ${
                    stop.isPrerequisite ? "ms-10" : ""
                  }`}
                >
                  {!isLast && (
                    <span
                      aria-hidden
                      className="absolute start-[16px] top-[26px] bottom-[-6px] w-px"
                      style={
                        nextIsUnlock
                          ? {
                              backgroundImage:
                                "repeating-linear-gradient(to bottom, var(--color-signal) 0 5px, transparent 5px 10px)",
                            }
                          : { background: "var(--color-rule)" }
                      }
                    />
                  )}

                  <span className="flex justify-center pt-2.5">
                    <span
                      aria-hidden
                      className="relative z-10 h-[15px] w-[15px] rounded-full border-2 bg-ink"
                      style={{
                        borderColor: isCurrent ? "var(--color-signal)" : s.stroke,
                        background: isCurrent ? "var(--color-ink)" : s.fill,
                        boxShadow: isCurrent ? "0 0 0 4px rgba(91,200,232,0.16)" : undefined,
                      }}
                    >
                      {isCurrent && <span className="absolute inset-[3px] rounded-full bg-signal" />}
                    </span>
                  </span>

                  <button
                    onClick={() => onNodeClick(node)}
                    className="flex flex-col gap-2 rounded-md border-2 px-4 py-3.5 text-start transition hover:border-signal-dim"
                    style={{
                      background: isCurrent ? "#16232b" : "var(--color-slab)",
                      borderColor: isCurrent ? "var(--color-signal)" : "var(--color-rule)",
                    }}
                  >
                    {stop.isPrerequisite && (
                      <span className="flex flex-wrap items-center gap-2 font-mono text-[10px] tracking-[0.06em] text-signal">
                        <span aria-hidden className="h-px w-4 bg-signal" />
                        {t.rail.addedAfterConfusion}
                        {stop.unlocksTitle && (
                          <span className="text-graphite">{t.map.unlocks(stop.unlocksTitle)}</span>
                        )}
                      </span>
                    )}

                    <span
                      className="font-display text-[17px] font-medium leading-[1.3] tracking-tight"
                      style={{ color: isCurrent ? "var(--color-signal)" : "var(--color-chalk)" }}
                    >
                      {node.title}
                    </span>

                    <span className="font-mono text-[11px] text-graphite">
                      {node.file}
                      {" · "}
                      {t.lesson.lines(node.line_start, node.line_end)}
                    </span>

                    <span className="flex flex-wrap items-center gap-1.5">
                      {node.concept_tags.map((tag) => {
                        const style = tagStyle(tag);
                        return (
                          <span
                            key={tag}
                            className="rounded-[2px] border px-1.5 py-px font-mono text-[9.5px] tracking-[0.05em]"
                            style={{
                              color: style.text,
                              borderColor: style.border,
                              background: style.background,
                            }}
                          >
                            {tagLabel(tag)}
                          </span>
                        );
                      })}
                      {node.weak_spot && (
                        <span className="font-mono text-[9.5px] tracking-[0.05em] text-rust">
                          {t.rail.markedWeak}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </section>
      </div>
    </div>
  );
}
