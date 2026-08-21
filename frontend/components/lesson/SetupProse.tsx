"use client";

import Prose from "@/components/ui/Prose";
import SectionLabel from "@/components/ui/SectionLabel";
import { t } from "@/lib/strings";

/**
 * The half of the lesson the learner reads before answering.
 *
 * `isSplit` is what distinguishes a B4-era lesson, which withholds its
 * explanation, from an older one that has a single body and nothing to withhold.
 * The label changes with it, which is why the flag is passed rather than derived
 * here: the panel knows whether `setup` exists.
 */
export default function SetupProse({
  isSplit,
  body,
}: {
  isSplit: boolean;
  body: string | null | undefined;
}) {
  return (
    <div className="flex flex-col gap-3">
      {/* A pre-B4 lesson has no halves to withhold, so it renders exactly as
          it always did, under the label it always had. */}
      <SectionLabel>{isSplit ? t.lesson.setup : t.lesson.walkthrough}</SectionLabel>
      {/* Markdown, because `agent.py` asks Teaching for markdown here. Printing
          the asterisks was never a rendering choice, only a missing renderer. */}
      <Prose text={body} size="body" tone="paper" />
    </div>
  );
}
