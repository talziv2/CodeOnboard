"use client";

import type { NodeGap } from "@/lib/api";
import Button from "@/components/ui/Button";
import SectionLabel from "@/components/ui/SectionLabel";
import { t } from "@/lib/strings";

/**
 * What the learner still does not know here, by name.
 *
 * §18.10 calls this the product's most honest surface: it says what is missing
 * rather than how much. Named, not counted — a count says how much is wrong, and
 * only the claim says what.
 *
 * The list is chosen by the panel, which prefers the just-graded reply over the
 * graph because the graph lags by one refresh on the warm-up path. That
 * preference stays there; this renders what it is given.
 *
 * §3a asks whether gaps should stay visible during feedback or collapse to a
 * counter the moment a verdict lands. Extracting does not answer that — L4 does.
 */
export default function GapList({
  gaps,
  onWaive,
  disabled = false,
}: {
  gaps: NodeGap[];
  onWaive: (gapId: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-col gap-3">
      <SectionLabel>{t.lesson.gapsHeading}</SectionLabel>
      <p className="text-meta text-graphite">{t.lesson.gapsHelp}</p>
      <ul className="flex flex-col gap-2">
        {gaps.map((gap) => (
          <li
            key={gap.id}
            className="flex items-start justify-between gap-3 rounded-card border border-rule bg-slab px-3 py-2"
          >
            <div className="flex flex-col gap-1">
              <span className="text-aside text-chalk">{gap.claim}</span>
              <span className="text-micro uppercase tracking-wide text-graphite">
                {gap.blocking ? t.lesson.gapBlocking : t.lesson.gapNonBlocking}
              </span>
            </div>
            <Button variant="secondary" size="xs" className="shrink-0"
              onClick={() => onWaive(gap.id)}
              disabled={disabled}
            >
              {t.lesson.waiveOne}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
