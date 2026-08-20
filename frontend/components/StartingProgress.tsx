"use client";

import { useEffect, useState } from "react";
import { sessionProgress } from "@/lib/api";
import type { PipelineProgress } from "@/lib/api";
import { t } from "@/lib/strings";

/**
 * The two-to-four minute wait, shown as what the pipeline is actually doing.
 *
 * The run reports every stage transition and every exploration tool call
 * (backend/pipeline/progress.py); this polls that on its own request while
 * /session/start is still in flight, so the stage list, the checkmarks and the
 * "Reading requests/sessions.py" line are all real events, not a timeline.
 *
 * Two things are not measured, and are handled rather than faked:
 *   - The bar is stages COMPLETED, never a percentage of unknown total work.
 *   - A stage with nothing to stream (a cached survey; the planning call, which
 *     is one opaque request) rotates a description of the work it is doing.
 *     Describing real work beats a number that creeps toward 100%.
 */

const POLL_MS = 900;
const HINT_MS = 4000;

/** How many read files to show. The count above the list is always the true total. */
const FILES_SHOWN = 6;
/** Five minutes: outside the two-to-four the normal line promises, not at its edge. */
const LONG_WAIT_S = 300;

interface Props {
  repoUrl: string;
  /** The id this run's /session/start was sent with. */
  progressId: string;
  /**
   * The goal the learner confirmed, kept on screen through the wait (P3).
   *
   * The synthesised goal rather than the raw question-and-answer list: the review
   * gate already showed the answers and made the learner confirm them, so this is
   * the version they agreed to. Optional, so the screen still renders for a caller
   * that has not got one.
   */
  goal?: Record<string, string> | null;
}

export default function StartingProgress({ repoUrl, progressId, goal }: Props) {
  const [snapshot, setSnapshot] = useState<PipelineProgress | null>(null);
  const [ticks, setTicks] = useState(0);
  const [hint, setHint] = useState(0);
  /**
   * Every file the exploration has opened, in the order it opened them.
   *
   * The backend streams one `activity` at a time and this screen used to render it
   * and throw it away, so a two-and-a-half-minute run showed perhaps forty real
   * facts about the learner's repository and left no trace of any of them. Kept in
   * a ref-like state and appended to, never recomputed: the snapshot only ever
   * carries the CURRENT activity, so the history exists nowhere else.
   *
   * `read_file` only. The other tools' targets are patterns, symbols and
   * directories; folding them into a list called "files" would make it something
   * the learner cannot check against their own checkout.
   */
  const [filesRead, setFilesRead] = useState<string[]>([]);

  // A local tick keeps the counter moving between polls, but it is not the
  // measure: browsers throttle timers in a hidden tab, and this wait is long
  // enough that people look away. The run's own elapsed time wins whenever we
  // have it — measured drifting to 8s against a real 118s with the tab hidden.
  useEffect(() => {
    const timer = setInterval(() => setTicks((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!progressId) return;
    let live = true;
    const poll = async () => {
      try {
        const next = await sessionProgress(progressId);
        if (!live) return;
        setSnapshot(next);
        const activity = next?.activity;
        if (activity?.tool === "read_file" && activity.target) {
          // Distinct, and order-preserving: the same file is often read twice in
          // a run, and a list that repeated it would look like a stutter rather
          // than like work.
          setFilesRead((seen) =>
            seen.includes(activity.target) ? seen : [...seen, activity.target]
          );
        }
      } catch {
        /* A 404 before the run registers, or a blip: this is a view of the
           request, and the request itself reports whether it worked. */
      }
    };
    poll();
    const timer = setInterval(poll, POLL_MS);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [progressId]);

  // Rotate the fallback lines. Reset on every stage change so a new stage opens
  // on its first line rather than mid-rotation.
  const stage = snapshot?.stage ?? null;
  useEffect(() => {
    setHint(0);
    const timer = setInterval(() => setHint((i) => i + 1), HINT_MS);
    return () => clearInterval(timer);
  }, [stage]);

  // Backend order when we have it, our own copy's order until then, so the
  // checklist is never empty and never invents a stage the pipeline dropped.
  const stages = snapshot?.stages ?? Object.keys(t.starting.stages);
  const done = new Set(snapshot?.done ?? []);
  const activity = snapshot?.activity ?? null;

  const detail = (): string => {
    if (activity) {
      const render = t.starting.activity[activity.tool];
      return render
        ? render(activity.target)
        : t.starting.activityUnknown(activity.target);
    }
    const lines = (stage && t.starting.hints[stage]) || [];
    return lines.length > 0 ? lines[hint % lines.length] : "";
  };

  return (
    <div className="flex w-full max-w-md flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
          {t.starting.label}
        </span>
        <h2 className="font-display text-head font-medium tracking-tight text-chalk">
          {repoUrl.replace(/^https?:\/\/github\.com\//, "")}
        </h2>
      </div>

      {/* CONTINUITY (P3). The interview vanished the instant the pipeline started,
          so a two-and-a-half-minute wait began with the screen forgetting what it
          was waiting for. The goal stays, one line of it, above the work being
          done for it. */}
      {goal?.primary_goal && (
        <div className="flex flex-col gap-1 border-s-2 border-rule ps-3">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
            {t.starting.goalHeading}
          </span>
          <p className="measure text-meta text-paper">{goal.primary_goal}</p>
        </div>
      )}

      {/* Stages completed, not a guess at how much is left. */}
      <div className="h-0.5 w-full overflow-hidden rounded-full bg-rule">
        <div
          className="h-full rounded-full bg-signal transition-[width] duration-700 ease-out"
          style={{ width: `${(done.size / Math.max(stages.length, 1)) * 100}%` }}
        />
      </div>

      <ul className="flex flex-col gap-2.5" role="status" aria-live="polite">
        {stages.map((key) => {
          const isDone = done.has(key);
          const isActive = key === stage;
          return (
            <li key={key} className="flex flex-col gap-1">
              <div
                className={`flex items-center gap-2.5 text-meta transition-colors ${
                  isDone ? "text-paper" : isActive ? "text-chalk" : "text-graphite"
                }`}
              >
                {isDone ? (
                  <span aria-hidden className="shrink-0 text-micro text-jade">
                    ✓
                  </span>
                ) : isActive ? (
                  <span
                    aria-hidden
                    className="h-[11px] w-[11px] shrink-0 animate-pulse rounded-full border-[1.5px] border-signal bg-signal/30"
                  />
                ) : (
                  <span
                    aria-hidden
                    className="h-[11px] w-[11px] shrink-0 rounded-full border-[1.5px] border-rule"
                  />
                )}
                {t.starting.stages[key] ?? key}
              </div>

              {isActive && (
                /* Churns several times a second — announcing it would talk over
                   the stage change, which is the part worth hearing. */
                <div aria-hidden className="flex items-baseline gap-2 ps-[21px]">
                  <span className="min-w-0 truncate font-mono text-micro text-signal/80">
                    {detail()}
                  </span>
                  {/* Only beside a stage that is making them: the count is the
                      run's total, and next to "Planning your route" — which
                      makes no lookups — it read as if planning were still
                      searching the repository. */}
                  {activity && (snapshot?.calls ?? 0) > 0 && (
                    <span className="shrink-0 font-mono text-micro text-graphite">
                      {t.starting.lookups(snapshot!.calls)}
                    </span>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {/* What it has actually read, accumulated (P3). Real streamed facts about the
          learner's own repository, which is the only thing on this screen that could
          not have been written in advance.

          Newest first, and capped: the list is evidence that work is happening, not
          a log to audit, and an unbounded column of paths would push the stages off
          a short viewport. The count above it stays honest whatever the cap. */}
      {filesRead.length > 0 && (
        <div className="flex flex-col gap-1.5 border-t border-rule pt-3">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
            {t.starting.filesRead(filesRead.length)}
          </span>
          <ul aria-hidden className="flex flex-col gap-0.5">
            {filesRead.slice(-FILES_SHOWN).reverse().map((path) => (
              <li key={path} className="truncate font-mono text-micro text-graphite">
                {path}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center gap-2.5 border-t border-rule pt-3">
        <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-signal" />
        <span className="font-mono text-micro text-graphite">
          {(() => {
            const seconds = Math.round(Math.max(ticks, snapshot?.seconds ?? 0));
            // Past the span the normal line promises, that line is no longer
            // reassurance — it is the screen insisting on something the learner can
            // see is false.
            return seconds >= LONG_WAIT_S
              ? t.starting.elapsedLong(seconds)
              : t.starting.elapsed(seconds);
          })()}
        </span>
      </div>
    </div>
  );
}
