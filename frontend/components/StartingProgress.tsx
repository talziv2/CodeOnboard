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

interface Props {
  repoUrl: string;
  /** The id this run's /session/start was sent with. */
  progressId: string;
}

export default function StartingProgress({ repoUrl, progressId }: Props) {
  const [snapshot, setSnapshot] = useState<PipelineProgress | null>(null);
  const [ticks, setTicks] = useState(0);
  const [hint, setHint] = useState(0);

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
        if (live) setSnapshot(next);
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
        <span className="font-mono text-[calc(10.5rem/16)] uppercase tracking-[0.14em] text-graphite">
          {t.starting.label}
        </span>
        <h2 className="font-display text-[calc(21rem/16)] font-medium tracking-tight text-chalk">
          {repoUrl.replace(/^https?:\/\/github\.com\//, "")}
        </h2>
      </div>

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
                className={`flex items-center gap-2.5 text-[calc(12.5rem/16)] transition-colors ${
                  isDone ? "text-paper" : isActive ? "text-chalk" : "text-graphite"
                }`}
              >
                {isDone ? (
                  <span aria-hidden className="shrink-0 text-[calc(11rem/16)] text-jade">
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
                  <span className="min-w-0 truncate font-mono text-[calc(11rem/16)] text-signal/80">
                    {detail()}
                  </span>
                  {/* Only beside a stage that is making them: the count is the
                      run's total, and next to "Planning your route" — which
                      makes no lookups — it read as if planning were still
                      searching the repository. */}
                  {activity && (snapshot?.calls ?? 0) > 0 && (
                    <span className="shrink-0 font-mono text-[calc(10rem/16)] text-graphite">
                      {t.starting.lookups(snapshot!.calls)}
                    </span>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <div className="flex items-center gap-2.5 border-t border-rule pt-3">
        <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-signal" />
        <span className="font-mono text-[calc(11rem/16)] text-graphite">
          {t.starting.elapsed(Math.round(Math.max(ticks, snapshot?.seconds ?? 0)))}
        </span>
      </div>
    </div>
  );
}
