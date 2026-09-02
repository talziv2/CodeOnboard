"use client";

import Prose from "@/components/ui/Prose";
import { BlockTitle } from "@/components/ui/SectionLabel";
import { BLOCK_ICON, LESSON_ICON } from "@/lib/lessonIcons";
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
      {/* The marker follows the same flag as the label: the two names are two
          different blocks as far as a reader is concerned, so a single glyph for
          both would be the marker claiming a sameness the label denies. They
          happen to resolve to the same glyph today because they are the same
          ROLE — the thing you read before answering — and `lessonIcons` says so
          beside the entry rather than here. */}
      <BlockTitle icon={isSplit ? BLOCK_ICON.setup : LESSON_ICON.walkthrough}>
        {isSplit ? t.lesson.setup : t.lesson.walkthrough}
      </BlockTitle>
      {/* Markdown, because `agent.py` asks Teaching for markdown here. Printing
          the asterisks was never a rendering choice, only a missing renderer. */}
      <Prose text={body} size="body" tone="paper" />
    </div>
  );
}
