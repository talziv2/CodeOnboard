"use client";

import { useMemo } from "react";
import type {
  Area, GraphNode, GraphEdge, Pattern, Progress, UnderstandingClass, UnderstandingProfile,
  UnderstandingRow, UnderstandingState,
} from "@/lib/api";
import {
  understandingLabel, understandingStyle, UNDERSTANDING_ORDER,
} from "@/lib/tags";
import { buildRoute } from "@/lib/graph-layout";
import {
  tagStyle, tagLabel, stateStyle, stateLabel, isCanonicalTag, STATE_ORDER,
} from "@/lib/tags";
import { t } from "@/lib/strings";

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  currentNodeId: string | null;
  /**
   * Computed server-side. The headline numbers are NOT derived from `nodes`
   * here: the definitions live in `backend/learning/progress.py`, and a second
   * implementation in the client is how the header and this view came to
   * disagree (learning-graph.md §5.6).
   */
  progress: Progress;
  /**
   * The Understanding Profile — computed server-side from the evidence. Two
   * dimensions per unit: what was demonstrated, and what the learner decided
   * about remediation. Never derived here.
   */
  understanding: UnderstandingProfile;
  /** Curriculum grouping. Empty on pre-B3 graphs, which group as one list. */
  areas?: Area[];
  repoUrl?: string;
  onNodeClick: (node: GraphNode) => void;
  /** Opens the evidence chain behind one unit's state. */
  onOpenEvidence: (nodeId: string) => void;
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
        <span className="shrink-0 font-mono text-[calc(10.5rem/16)] tabular-nums text-graphite">
          {sublabel ?? `${tally.understood}/${total}`}
        </span>
      </span>
      <StateStrip tally={tally} total={total} />
    </li>
  );
}

/** Profile rows grouped by area, preserving walk order within each group. */
function groupRows(rows: UnderstandingRow[]): Record<string, UnderstandingRow[]> {
  const groups: Record<string, UnderstandingRow[]> = {};
  for (const row of rows) (groups[row.area_id ?? ""] ??= []).push(row);
  return groups;
}

/** Pre-B3 graphs have no areas, so an unnamed group is normal, not an error. */
function areaTitle(areas: Area[] | undefined, areaId: string): string {
  return areas?.find((a) => a.id === areaId)?.title ?? t.map.theRoute;
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3.5 rounded-md border border-rule bg-slab p-4">
      <h3 className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.16em] text-graphite">{title}</h3>
      {children}
    </section>
  );
}

/**
 * One unit as a pip, coloured by what the evidence shows. Clicking it opens the
 * evidence behind that colour — no claim the learner cannot inspect.
 */
function Pip({ row, onOpen }: { row: UnderstandingRow; onOpen: () => void }) {
  const style = understandingStyle(row.understanding);
  return (
    <button
      onClick={onOpen}
      title={`${row.title} — ${understandingLabel(row.understanding)}`}
      aria-label={`${row.title} — ${understandingLabel(row.understanding)}`}
      className="h-[calc(13rem/16)] w-[calc(13rem/16)] shrink-0 rounded-full border-[1.5px] transition hover:scale-125"
      style={{ borderColor: style.stroke, background: style.fill }}
    />
  );
}

/** A named list of units, each opening its own evidence. Used by all three
 *  outcome bands, which differ in meaning rather than in shape. */
function UnitList({
  rows, onOpen, tone,
}: {
  rows: UnderstandingRow[];
  onOpen: (id: string) => void;
  tone?: string;
}) {
  return (
    <ul className="flex flex-col gap-2">
      {rows.map((row) => (
        <li key={row.node_id}>
          <button
            onClick={() => onOpen(row.node_id)}
            className="flex w-full flex-col gap-0.5 rounded border border-rule bg-slab px-3 py-2 text-start transition hover:border-signal-dim"
          >
            <span
              className="text-[calc(12.5rem/16)] font-medium leading-snug"
              style={{ color: tone ?? "var(--color-chalk)" }}
            >
              {row.title}
            </span>
            <span className="font-mono text-[calc(10rem/16)] text-graphite">
              {row.attempts === 1
                ? t.map.ofAssessed(1, 1).replace("1 of 1", "1 answer")
                : `${row.attempts} answers`}
              {row.disposition !== "active" && (
                <> · {t.map.disposition[row.disposition] ?? row.disposition}</>
              )}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/** The sentence for one pattern, composed here so all wording stays in `strings`. */
function patternSentence(pattern: Pattern): string {
  const d = pattern.detail;
  switch (pattern.template) {
    case "kind_contrast":
      return t.map.pattern.kind_contrast(
        tagLabel(String(d.lead_kind)), Number(d.lead_extra), Number(d.lead_total),
        tagLabel(String(d.base_kind)), Number(d.base_extra), Number(d.base_total)
      );
    case "recurring_shortfall":
      return t.map.pattern.recurring_shortfall(
        Number(d.attempts), Number(d.nodes),
        t.map.shortfall[String(d.gap_kind)] ?? String(d.gap_kind)
      );
    case "area_evidence":
      return t.map.pattern.area_evidence(
        Number(d.demonstrated), Number(d.assessed), String(d.area_title)
      );
    default:
      return "";
  }
}

/**
 * One observation, with its evidence one click away.
 *
 * No dismiss, no "not useful", no feedback control — OQ-5, decided 2026-08-18.
 * These are deterministic aggregates over evidence the learner can inspect, not
 * diagnoses of them, so there is nothing to contest; offering a rebuttal would
 * imply the card is an opinion. Feedback arrives with L3 interpretations, where
 * the system genuinely infers rather than counts.
 */
function PatternCard({
  pattern, onOpen,
}: { pattern: Pattern; onOpen: (nodeId: string) => void }) {
  const setAside = Number(pattern.detail.set_aside ?? 0);
  return (
    <li className="flex flex-col gap-2 rounded border border-rule bg-slab px-3.5 py-3">
      <p className="text-[calc(12.5rem/16)] leading-relaxed text-paper">
        {patternSentence(pattern)}
        {/* Keeps the aggregate from reading as outstanding work when part of it
            is something the learner already declined to pursue. */}
        {setAside > 0 && (
          <span className="text-graphite"> {t.map.pattern.setAsideNote(setAside)}</span>
        )}
      </p>
      <span className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.13em] text-graphite">
          {t.map.patternEvidence(pattern.evidence.length)}
        </span>
        {/* Reuses the evidence drawer rather than inventing a second
            explanation surface: one unit, one place its story is told. */}
        {pattern.evidence.map((ref, i) => (
          <button
            key={`${ref.node_id}-${ref.attempt_index}`}
            onClick={() => onOpen(ref.node_id)}
            className="rounded-[2px] border border-rule px-1.5 py-px font-mono text-[calc(9.5rem/16)] text-graphite transition hover:border-signal-dim hover:text-signal"
          >
            {i + 1}
          </button>
        ))}
      </span>
    </li>
  );
}

export default function MapView({
  nodes, edges, currentNodeId, progress, understanding, areas, repoUrl,
  onNodeClick, onOpenEvidence,
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
    };
  }, [nodes]);

  // The three outcome bands. Server-classified, so nothing here decides what
  // counts as a weakness — and `recovered` can never leak into `needs work`,
  // because the backend put each id in exactly one bucket.
  const byId = useMemo(
    () => new Map(understanding.nodes.map((r) => [r.node_id, r])),
    [understanding.nodes]
  );
  const pick = (ids: string[]) =>
    ids.map((id) => byId.get(id)).filter((r): r is UnderstandingRow => Boolean(r));
  const needsWork = pick(understanding.needs_work);
  const setAside = pick(understanding.set_aside);
  const recovered = pick(understanding.recovered);

  const pct = Math.round(progress.goal_readiness * 100);
  const repo = repoUrl?.replace(/^https?:\/\/github\.com\//, "").replace(/\.git$/, "");

  return (
    <div className="h-full overflow-y-auto px-6 py-7">
      <div className="mx-auto flex max-w-4xl flex-col gap-7">

        {/* headline */}
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div className="flex flex-col gap-1">
            <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.16em] text-graphite">
              {t.map.label}
            </span>
            <h2 className="font-display text-[calc(25rem/16)] font-medium leading-tight tracking-tight text-chalk">
              {repo ?? t.map.thisCodebase}
            </h2>
            {/* The headline sentence states the GOAL measure over the required
                set, then the journey beside it — the two answer different
                questions and neither stands alone (§5.4). Detours and skips are
                named rather than folded into a percentage, so a low number is
                explainable instead of arbitrary (OQ-2). */}
            <p className="text-[calc(12.5rem/16)] text-graphite">
              {t.map.coreDemonstrated(progress.core_understood, progress.core_total)}
              {" · "}
              {t.map.stopsTaken(progress.stops_settled, progress.stops_total)}
              {progress.detours.length > 0 && (
                <> · {t.map.detoursTaken(progress.detours.length)}</>
              )}
              {progress.skipped > 0 && <> · {t.map.skippedStops(progress.skipped)}</>}
            </p>
            {/* The honest denominator for everything below: a profile over 16
                units where 3 carry evidence is a profile of 3. */}
            <p className="font-mono text-[calc(10.5rem/16)] text-graphite">
              {t.map.assessedOf(understanding.assessed, understanding.total)}
            </p>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="font-display text-[calc(34rem/16)] leading-none tabular-nums text-signal">
              {pct}%
            </span>
            <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.14em] text-graphite">
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
                className="flex items-center gap-2 font-mono text-[calc(10.5rem/16)] text-graphite"
              >
                <span
                  aria-hidden
                  className="h-[calc(9rem/16)] w-[calc(9rem/16)] shrink-0 rounded-full border-[1.5px]"
                  style={{ borderColor: stateStyle(state).stroke, background: stateStyle(state).fill }}
                />
                <span className="tabular-nums text-chalk">{summary.overall[state]}</span>
                {stateLabel(state)}
              </span>
            ))}
          </div>
        </div>

        {/* ── UNDERSTANDING PROFILE ──────────────────────────────────────────
            What the evidence demonstrates, grouped by AREA — the curriculum's
            own grouping, which the rail already uses. A file is where code
            happens to live; an area is what the journey is about. */}
        <Panel title={t.map.profileTitle}>
          {understanding.assessed === 0 ? (
            <p className="text-[calc(12.5rem/16)] leading-relaxed text-graphite">
              {t.map.noEvidenceYet}
            </p>
          ) : (
            <>
              <div className="flex flex-wrap gap-x-5 gap-y-1.5">
                {UNDERSTANDING_ORDER.map((state) => {
                  const style = understandingStyle(state);
                  return (
                    <span
                      key={state}
                      className="flex items-center gap-2 font-mono text-[calc(10.5rem/16)] text-graphite"
                    >
                      <span
                        aria-hidden
                        className="h-[calc(9rem/16)] w-[calc(9rem/16)] shrink-0 rounded-full border-[1.5px]"
                        style={{ borderColor: style.stroke, background: style.fill }}
                      />
                      <span className="tabular-nums text-chalk">
                        {understanding.totals[state]}
                      </span>
                      {understandingLabel(state)}
                    </span>
                  );
                })}
              </div>

              <ul className="flex flex-col gap-3 border-t border-rule pt-3">
                {Object.entries(groupRows(understanding.nodes)).map(([areaId, rows]) => (
                  <li key={areaId} className="flex flex-col gap-1.5">
                    <span className="flex items-baseline justify-between gap-3">
                      <span className="min-w-0 truncate font-mono text-[calc(11rem/16)] text-paper">
                        {areaTitle(areas, areaId)}
                      </span>
                      <span className="shrink-0 font-mono text-[calc(10.5rem/16)] tabular-nums text-graphite">
                        {t.map.ofAssessed(
                          rows.filter((r) => r.understanding === "strength"
                            || r.understanding === "recovered").length,
                          rows.length
                        )}
                      </span>
                    </span>
                    {/* Every pip is one unit, and clicking it shows the evidence
                        that produced its colour. */}
                    <span className="flex flex-wrap gap-1.5">
                      {rows.map((row) => (
                        <Pip key={row.node_id} row={row} onOpen={() => onOpenEvidence(row.node_id)} />
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>

        {/* ── NEEDS WORK / WORKED THROUGH / SET ASIDE ─────────────────────────
            Three bands, adjacent on purpose. Separating "still open" from
            "worked through" is the point of the milestone; putting them side by
            side is what stops the second reading as the first. */}
        {(needsWork.length > 0 || recovered.length > 0 || setAside.length > 0) && (
          <div className="grid gap-4 md:grid-cols-2">
            {needsWork.length > 0 && (
              <Panel title={`${t.map.needsWork} · ${needsWork.length}`}>
                <UnitList rows={needsWork} onOpen={onOpenEvidence} tone="var(--color-rust)" />
              </Panel>
            )}

            {recovered.length > 0 && (
              <Panel title={`${t.map.workedThrough} · ${recovered.length}`}>
                <p className="text-[calc(11.5rem/16)] leading-snug text-graphite">
                  {t.map.workedThroughHint}
                </p>
                <UnitList rows={recovered} onOpen={onOpenEvidence} />
              </Panel>
            )}

            {/* Unresolved, and the learner closed the question. Kept visible so
                the truth survives, kept OUT of "needs work" so it does not nag
                about a decision already made. */}
            {setAside.length > 0 && (
              <Panel title={`${t.map.setAside} · ${setAside.length}`}>
                <p className="text-[calc(11.5rem/16)] leading-snug text-graphite">
                  {t.map.setAsideHint}
                </p>
                <UnitList rows={setAside} onOpen={onOpenEvidence} />
              </Panel>
            )}
          </div>
        )}

        {/* ── PATTERNS ────────────────────────────────────────────────────────
            A deeper interpretation layer, so it sits BELOW the outcome bands
            and never competes with them. Renders only when a threshold is met;
            otherwise one restrained line, because at the measured session size
            most sessions will legitimately have no pattern at all. */}
        <Panel title={t.map.patterns}>
          {understanding.patterns.length === 0 ? (
            <p className="text-[calc(12rem/16)] leading-relaxed text-graphite">
              {t.map.patternsEmpty}
            </p>
          ) : (
            <ul className="flex flex-col gap-2.5">
              {understanding.patterns.map((pattern) => (
                <PatternCard
                  key={pattern.template}
                  pattern={pattern}
                  onOpen={onOpenEvidence}
                />
              ))}
            </ul>
          )}
        </Panel>

        {/* the two breakdowns that make this a reflection view rather than a list */}
        <div className="grid gap-4 md:grid-cols-2">
          <Panel title={t.map.byKind}>
            <ul className="flex flex-col gap-3">
              {summary.kinds.map(([tag, tally, total]) => (
                <BreakdownRow
                  key={tag}
                  label={<span className="font-mono text-[calc(11rem/16)]">{tagLabel(tag)}</span>}
                  accent={tagStyle(tag).text}
                  tally={tally}
                  total={total}
                />
              ))}
            </ul>

            {summary.topics.length > 0 && (
              <div className="flex flex-col gap-2 border-t border-rule pt-3">
                <span className="font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.14em] text-graphite">
                  {t.map.topicsTouched}
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {summary.topics.map(([tag, tally, total]) => (
                    <span
                      key={tag}
                      title={t.map.understoodOfTotal(tally.understood, total)}
                      className="rounded-[2px] border border-rule px-1.5 py-px font-mono text-[calc(9.5rem/16)] tracking-[0.05em] text-graphite"
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
                    <span className="block truncate text-start font-mono text-[calc(11rem/16)] text-paper">
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
          <h3 className="flex items-center gap-2.5 font-mono text-[calc(10rem/16)] uppercase tracking-[0.16em] text-graphite">
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
                  className={`relative grid grid-cols-[calc(34rem/16)_1fr] gap-4 pb-5 ${
                    stop.isPrerequisite ? "ms-10" : ""
                  }`}
                >
                  {!isLast && (
                    <span
                      aria-hidden
                      className="absolute start-[calc(16rem/16)] top-[calc(26rem/16)] bottom-[calc(-6rem/16)] w-px"
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
                      className="relative z-10 h-[calc(15rem/16)] w-[calc(15rem/16)] rounded-full border-2 bg-ink"
                      style={{
                        borderColor: isCurrent ? "var(--color-signal)" : s.stroke,
                        background: isCurrent ? "var(--color-ink)" : s.fill,
                        boxShadow: isCurrent ? "0 0 0 4px var(--color-signal-halo)" : undefined,
                      }}
                    >
                      {isCurrent && <span className="absolute inset-[calc(3rem/16)] rounded-full bg-signal" />}
                    </span>
                  </span>

                  <button
                    onClick={() => onNodeClick(node)}
                    className="flex flex-col gap-2 rounded-md border-2 px-4 py-3.5 text-start transition hover:border-signal-dim"
                    style={{
                      background: isCurrent ? "var(--color-signal-wash)" : "var(--color-slab)",
                      borderColor: isCurrent ? "var(--color-signal)" : "var(--color-rule)",
                    }}
                  >
                    {stop.isPrerequisite && (
                      <span className="flex flex-wrap items-center gap-2 font-mono text-[calc(10rem/16)] tracking-[0.06em] text-signal">
                        <span aria-hidden className="h-px w-4 bg-signal" />
                        {t.rail.addedAfterConfusion}
                        {stop.unlocksTitle && (
                          <span className="text-graphite">{t.map.unlocks(stop.unlocksTitle)}</span>
                        )}
                      </span>
                    )}

                    <span
                      className="font-display text-[calc(17rem/16)] font-medium leading-[1.3] tracking-tight"
                      style={{ color: isCurrent ? "var(--color-signal)" : "var(--color-chalk)" }}
                    >
                      {node.title}
                    </span>

                    <span className="font-mono text-[calc(11rem/16)] text-graphite">
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
                            className="rounded-[2px] border px-1.5 py-px font-mono text-[calc(9.5rem/16)] tracking-[0.05em]"
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
                      {/* CURRENT state, not the sticky flag. `weak_spot` stays
                          true forever once set, so rendering it captioned a unit
                          the learner has since mastered as a weakness. */}
                      {node.understanding && node.understanding !== "insufficient" && (
                        <span
                          className="font-mono text-[calc(9.5rem/16)] tracking-[0.05em]"
                          style={{ color: understandingStyle(node.understanding).stroke }}
                        >
                          {understandingLabel(node.understanding)}
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
