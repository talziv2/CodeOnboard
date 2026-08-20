"use client";

import { t } from "@/lib/strings";

interface Props {
  goal: Record<string, string>;
  /** Stops on the promised walk, and how many chapters they fall into. */
  stops: number;
  areas: number;
}

/**
 * The learner's ID — who the system thinks it is teaching.
 *
 * Every line is DERIVED from the interview answers, in the browser, with no
 * model involved: `familiarity` and `code_depth` are fixed options, the rest is
 * the reader's own prose. That is the point of showing it. These five values are
 * what calibrate the Mentor's plan and every Teaching prompt, so a learner who
 * disagrees with the card is looking at exactly the thing to change — and can,
 * by starting over with different answers.
 *
 * The goal-type follow-ups (the change they want to make, the error they are
 * chasing) are shown when present: they are the most specific thing in the
 * profile, and only one goal_type ever fills each of them.
 */
export default function ProfileCard({ goal, stops, areas }: Props) {
  const familiarity =
    t.welcome.familiarity[goal.familiarity] ?? goal.familiarity ?? null;
  const goalType = t.welcome.goalType[goal.goal_type] ?? goal.goal_type ?? null;
  const depth =
    t.welcome.codeDepth[goal.code_depth] ??
    t.session.depth[goal.depth] ??
    goal.depth ??
    null;

  // Rendered as one list so an absent follow-up leaves no gap in the layout.
  const rows: Array<[string, string]> = [];
  if (goal.primary_goal) rows.push([t.welcome.goalLabel, goal.primary_goal]);
  if (goal.focus_area) rows.push([t.welcome.focusLabel, goal.focus_area]);
  if (goal.background) rows.push([t.welcome.backgroundLabel, goal.background]);
  for (const key of [
    "change_target",
    "risk_tolerance",
    "contribution_context",
    "error_description",
    "tried_so_far",
  ] as const) {
    const value = goal[key];
    if (value) rows.push([t.welcome.followups[key] ?? key, value]);
  }

  return (
    <aside className="flex flex-col gap-4 rounded-card border border-rule bg-slab p-5 shadow-card">
      <div className="flex flex-col gap-1">
        <span className="font-mono text-micro uppercase tracking-[0.16em] text-signal">
          {t.welcome.profileLabel}
        </span>
        <p className="text-meta text-graphite">
          {t.welcome.profileNote}
        </p>
      </div>

      {/* The three fixed dials, as chips: each is one of a small set of values,
          and together they are what "personalized" actually means here. */}
      <div className="flex flex-wrap gap-1.5">
        {[goalType, familiarity, depth].filter(Boolean).map((chip) => (
          <span
            key={chip}
            className="rounded-field border border-signal-dim bg-signal-halo px-2 py-1 font-mono text-micro text-signal"
          >
            {chip}
          </span>
        ))}
      </div>

      <dl className="flex flex-col gap-3 border-t border-rule pt-4">
        {rows.map(([label, value]) => (
          <div key={label} className="flex flex-col gap-0.5">
            <dt className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
              {label}
            </dt>
            <dd className="text-meta text-paper">
              {value}
            </dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-col gap-0.5 border-t border-rule pt-4">
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
          {t.welcome.routeLabel}
        </span>
        <span className="font-mono text-meta tabular-nums text-chalk">
          {t.welcome.routeCount(stops, areas)}
        </span>
      </div>
    </aside>
  );
}
