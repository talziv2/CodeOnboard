"use client";

import Prose from "@/components/ui/Prose";
import type { SupersededExplanation } from "@/lib/lessonHistory";
import { t } from "@/lib/strings";

/**
 * The explanations a re-teach replaced, oldest first.
 *
 * R3's third mitigation, and the one that decides whether Lesson accumulates. The
 * other two are already true: a re-teach REPLACES rather than appends, and at most
 * one section is expanded as new. This keeps the replaced versions reachable without
 * putting them on the page.
 *
 * WHY KEEP THEM AT ALL. A re-teach happens because the learner misunderstood, so the
 * prose that misled them is half of how their understanding moved — the backend
 * keeps `superseded_lesson` for exactly that reason. Dropping it client-side would
 * throw away the more interesting half of the pair while the server still holds it.
 *
 * EACH VERSION NAMES THE ANSWER THAT REPLACED IT, which is what makes this a record
 * rather than a pile. "Version 1, replaced after you answered X" is a sentence about
 * the learner; "an older explanation" is filler.
 *
 * Rendered inside one always-collapsed disclosure — see `lessonBlocks.earlier`, which
 * has no `open` state in any phase.
 */
export default function EarlierExplanations({
  versions,
}: {
  versions: SupersededExplanation[];
}) {
  return (
    <div className="flex flex-col gap-5">
      {versions.map((version) => (
        <div key={`${version.version}-${version.at}`} className="flex flex-col gap-2">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
            {t.lesson.earlierVersion(version.version)}
          </span>

          {/* The answer first: it is the reason this version stopped being current,
              and reading the prose without it is reading it out of context. */}
          <div className="flex flex-col gap-1 border-s-2 border-rule ps-3">
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
              {t.lesson.earlierBecause}
            </span>
            <p className="measure whitespace-pre-wrap text-meta text-graphite">
              {version.answer}
            </p>
          </div>

          {version.setup && (
            <Prose text={version.setup} size="aside" tone="paper" />
          )}
          {version.reveal && (
            <Prose text={version.reveal} size="aside" tone="paper" />
          )}
        </div>
      ))}
    </div>
  );
}
