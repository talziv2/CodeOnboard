"use client";

import Callout from "@/components/ui/Callout";
import Prose from "@/components/ui/Prose";
import SectionLabel from "@/components/ui/SectionLabel";
import { t } from "@/lib/strings";

/**
 * The explanation, plus what to take from it and what it makes the learner
 * responsible for.
 *
 * WITHHELD UNTIL AN ANSWER EXISTS, and that withholding IS the active-learning
 * mechanism — not a UI flourish. The panel decides when: on a graded answer, and
 * also on a revisit, because someone returning to a node they already answered is
 * reading rather than being tested and hiding it from them would be friction
 * dressed as pedagogy.
 *
 * §3a asks whether `takeaway` and `ownership` belong beside the explanation at all,
 * or are a third thing competing with both the verdict and the reveal. They are
 * left exactly where they were; L4 answers that.
 */
export default function RevealBlock({
  reveal,
  takeaway,
  ownership,
}: {
  reveal: string;
  takeaway?: string | null;
  ownership?: string | null;
}) {
  return (
    <div className="flex flex-col gap-3">
      <SectionLabel>{t.lesson.reveal}</SectionLabel>
      <Prose text={reveal} size="body" tone="paper" />

      {takeaway && (
        <Callout tone="signal" label={t.lesson.takeaway} className="mt-1">
          <Prose text={takeaway} size="aside" tone="chalk" />
        </Callout>
      )}

      {ownership && (
        <Callout tone="neutral" label={t.lesson.ownership}>
          <Prose text={ownership} size="meta" tone="paper" />
        </Callout>
      )}
    </div>
  );
}
