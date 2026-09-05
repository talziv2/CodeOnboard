"use client";

import SectionLabel from "@/components/ui/SectionLabel";
import type { Contribution, GraphNode } from "@/lib/api";
import { t } from "@/lib/strings";

/**
 * The contribution scope card, on the welcome page.
 *
 * The demo moment, and the one screen where goal-directed learning is visible as
 * a fact rather than as a claim: the task the learner typed, the number of
 * concepts the plan says that task requires, those concepts by name, and — when
 * there is defensible evidence for it — what the plan left out.
 *
 * THE COUNT IS NEVER WRITTEN DOWN. It is `contribution.ready.required`, which is
 * `len(core_nodes(graph))` on the server — the same required set `goal_readiness`
 * divides by. A constant here, or a `nodes.filter(...)` here, would be a second
 * definition of "required" in the client, which is exactly how the header and
 * the map came to disagree (D22).
 *
 * THE SKIPPED LIST IS EVIDENCE-BOUND, and the guard is `skipped.length > 0`
 * rather than a placeholder. `backend/learning/coverage.py` returns only
 * subsystems the Layer-B survey itself named whose files no curriculum anchor
 * touches, and returns nothing at all when there is no survey to reason from.
 * "We skipped nothing" and "we cannot say what we skipped" are different claims
 * and neither is worth a heading with an empty list under it.
 */
export default function ScopeCard({
  contribution,
  requiredNodes,
  skipped,
}: {
  contribution: Contribution;
  /** The required stops, in walk order — the same units the rail is about to show. */
  requiredNodes: GraphNode[];
  skipped: { name: string; reason: string }[];
}) {
  const required = contribution.ready.required;
  if (!contribution.available || required === 0) return null;

  return (
    <section className="flex flex-col gap-5 rounded-panel border border-rule bg-well p-6">
      <SectionLabel tone="raised">{t.contribution.cardLabel}</SectionLabel>

      <div className="flex flex-col gap-2">
        <h2 className="text-title text-chalk">{t.contribution.cardHeading}</h2>
        <p className="font-mono text-micro uppercase tracking-[0.16em] text-graphite">
          {t.contribution.taskLabel}
        </p>
        {/* LEARNER-WRITTEN TEXT IS NEVER MARKDOWN (D23). The task is what they
            typed into the interview, so it is shown exactly as typed. */}
        <p className="whitespace-pre-wrap text-body text-paper">
          {contribution.task}
        </p>
      </div>

      <p className="text-lede text-chalk">
        {t.contribution.requiredHeading(required)}
      </p>

      <div className="flex flex-col gap-2">
        <SectionLabel>{t.contribution.requiredLabel}</SectionLabel>
        <ul className="flex flex-col gap-1.5">
          {requiredNodes.map((node) => (
            <li key={node.id} className="flex gap-2.5 text-aside text-paper">
              <span aria-hidden className="text-graphite">·</span>
              <span>{node.title}</span>
            </li>
          ))}
        </ul>
      </div>

      {skipped.length > 0 && (
        <div className="flex flex-col gap-2">
          <SectionLabel>{t.contribution.skippedLabel}</SectionLabel>
          <ul className="flex flex-col gap-1.5">
            {skipped.map((area) => (
              <li key={area.name} className="flex gap-2.5 text-aside text-graphite">
                <span aria-hidden>·</span>
                <span>
                  {area.name}
                  {area.reason ? ` — ${area.reason}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="font-mono text-micro text-graphite">
        {t.contribution.generatedNote}
      </p>
    </section>
  );
}
