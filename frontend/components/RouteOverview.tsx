"use client";

import type { RouteSection } from "@/lib/route-sections";
import SectionLabel from "@/components/ui/SectionLabel";
import { t } from "@/lib/strings";

/**
 * The route, at chapter granularity, on the briefing page.
 *
 * P4. The briefing said what the repository is and what the goal was taken to be,
 * and then asked the learner to start — without ever showing them what they had
 * agreed to walk. This is that: the chapters, in order, with how many stops each
 * holds.
 *
 * ── Built from `splitJourney`, not from `areas` ───────────────────────────────
 *
 * The sections are computed by the same function the rail uses, and passed in
 * already grouped. That is deliberate rather than convenient: the rail and this
 * list are two renderings of one route, and computing the grouping twice is how
 * they would come to disagree about which chapter a stop belongs to — or about how
 * many there are, once `prune_ahead` and the scope control start moving units
 * between buckets. One source, two views.
 *
 * It also inherits `buildSections`'s handling of the ungrouped case for free: a
 * pre-B3 graph has no areas, `splitJourney` returns one section with no `area`, and
 * this renders it as a plain list of stops with no chapter heading — which is what
 * a route with no chapters is.
 *
 * ── Chapter granularity, and why not stop titles ──────────────────────────────
 *
 * Fourteen stop titles is a table of contents nobody reads before starting, and it
 * makes the briefing look like the work rather than the introduction to it. The
 * chapter titles plus a count say the same thing at the scale a decision is made
 * at: is this the right shape, and is it about the right size?
 */
export default function RouteOverview({
  sections,
  optional,
}: {
  sections: RouteSection[];
  /** Stops the planner marked `optional` — off the default walk, still reachable. */
  optional: number;
}) {
  const stops = sections.reduce((n, s) => n + s.stops.length, 0);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <SectionLabel>{t.welcome.routeLabel}</SectionLabel>
        <span className="font-mono text-micro text-graphite">
          {t.welcome.routeCount(stops, sections.filter((s) => s.area).length)}
        </span>
      </div>

      <ol className="flex flex-col">
        {sections.map((section, index) => (
          <li
            key={section.area?.id ?? `ungrouped-${index}`}
            className="flex gap-3 border-s border-rule ps-4 pb-4 last:pb-0"
          >
            {/* The number is the reading order, which is the only claim this list
                makes about sequence. Chapters are walked in order; stops within
                one are the rail's business. */}
            <span className="mt-px shrink-0 font-mono text-micro text-graphite">
              {String(index + 1).padStart(2, "0")}
            </span>
            <span className="flex min-w-0 flex-col gap-1">
              <span className="text-aside text-paper">
                {section.area?.title ?? t.welcome.routeUngrouped}
              </span>
              {/* The chapter's own reason, when the planner gave one. Not
                  invented where it did not: a chapter with no `why` shows its
                  stop count and nothing else. */}
              {section.area?.why && (
                <span className="measure text-meta text-graphite">{section.area.why}</span>
              )}
              {/* Only for a NAMED chapter. An unnamed section is the whole route,
                  so its count is the summary's count — saying it twice, one line
                  apart, reads as two different facts that happen to agree. */}
              {section.area && (
                <span className="font-mono text-micro text-graphite">
                  {t.welcome.routeStops(section.stops.length)}
                </span>
              )}
            </span>
          </li>
        ))}
      </ol>

      {/* Said here because the count above excludes them, and a learner who later
          finds extra stops in the rail should have been told they existed. */}
      {optional > 0 && (
        <span className="font-mono text-micro text-graphite">
          {t.welcome.routeOptional(optional)}
        </span>
      )}
    </div>
  );
}
