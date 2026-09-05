"use client";

import type { ImplementationRail, StepView } from "@/lib/contribution";
import { t } from "@/lib/strings";

/**
 * THE SESSION COLUMN'S CHROME DURING THE IMPLEMENTATION PHASE.
 *
 *   ┌ Contribution                       Back to the journey · Show source ┐
 *   └ Plan · Locate · Continue in Claude                                   ┘
 *
 * It REPLACES `SurfaceTabs` rather than sitting beside it, and that is the whole
 * point. `Learn / Route` and `Lesson / Understanding` are the learning phase's
 * navigation: they choose which view of a *stop* you are reading. During
 * Plan → Locate → Continue in Claude there is no stop on screen, so those
 * controls name views that do not exist here — and a learner who pressed
 * `Understanding` during the handoff got the understanding surface of whichever
 * node happened to be current, which is a different phase of the session
 * appearing under implementation chrome.
 *
 * NOT HIDDEN WITH CSS. The page renders one bar or the other, chosen by
 * `centreSurface` — the same decision that chooses the column beneath it, so the
 * chrome and the content cannot describe different phases.
 *
 * The rail model is passed in rather than recomputed: `implementationRail` also
 * draws the route rail's Implementation section, so the step the header marks
 * current and the step the sidebar marks current are one fact (DI-1).
 *
 * Geometry deliberately mirrors `SurfaceTabs`: a mode-ish row on `slab` with the
 * trailing group, and a tab row underneath carrying the underline. Same shape,
 * so crossing the phase boundary does not look like arriving in a different
 * application.
 */
export default function ImplementationBar({
  rail,
  onStep,
  trailing,
}: {
  rail: ImplementationRail;
  onStep: (step: StepView) => void;
  /** The right-hand group — the way back to the journey, `Show source`. */
  trailing?: React.ReactNode;
}) {
  return (
    <>
      <div className="flex shrink-0 items-center gap-3 border-b border-rule bg-slab px-5 py-2">
        {/* Names the phase, and does not offer to leave it: the way back is a
            labelled control in the trailing group, not a second mode switch. */}
        <span className="font-mono text-micro uppercase tracking-[0.13em] text-signal">
          {t.contribution.railTitle}
        </span>
        {trailing && <span className="ms-auto flex items-center gap-3">{trailing}</span>}
      </div>

      <div
        role="group"
        aria-label={t.contribution.railTitle}
        className="flex shrink-0 items-center gap-1 border-b border-rule px-5"
      >
        {rail.stages.map((row) => {
          const current = row.state === "current";
          return (
            <button
              key={row.stage}
              onClick={row.enterable ? () => onStep(row.stage) : undefined}
              // NOT a disabled button. A step that cannot be entered yet is not a
              // control that failed; `aria-disabled` plus no handler says "not
              // yet" without the dead-click a `disabled` attribute produces.
              aria-disabled={!row.enterable || undefined}
              aria-current={current ? "step" : undefined}
              // `aria-current="step"` rather than `"page"`: these are stages of
              // one task, not separate views of it — the distinction `SurfaceTabs`
              // makes between its own two levels.
              className={`-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2.5 font-mono text-micro uppercase tracking-[0.13em] transition ${
                current
                  ? "border-signal text-signal"
                  : row.state === "done"
                    ? "border-transparent text-graphite hover:text-chalk"
                    : "border-transparent text-muted"
              }`}
            >
              {t.contribution.stages[row.stage]}
            </button>
          );
        })}
      </div>
    </>
  );
}
