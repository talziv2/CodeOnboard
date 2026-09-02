"use client";

import type { Anchor } from "@/lib/api";
import { BlockTitle } from "@/components/ui/SectionLabel";
import { BLOCK_ICON, LESSON_ICON } from "@/lib/lessonIcons";
import { t } from "@/lib/strings";

/**
 * A unit anchored on more than one place in the code, as an ordered walk.
 *
 * Each step hands over ITS OWN file and line range, which is the whole point:
 * before `viewingRange` existed, step 2 of a flow opened the right file at the
 * node's display range. That contract is preserved here verbatim — the range
 * comes from the anchor, never from the node.
 */
export default function TracePath({
  anchors,
  onFileClick,
}: {
  anchors: Anchor[];
  onFileClick: (file: string, lineStart?: number, lineEnd?: number) => void;
}) {
  // One place is not a path. The label and the step prefix both stop claiming an
  // order that does not exist — which is what let this render for every unit
  // instead of only the multi-anchor ones.
  const isPath = anchors.length > 1;

  return (
    <div data-tour="code-links" className="flex flex-col gap-2">
      <BlockTitle icon={isPath ? BLOCK_ICON.tracePath : LESSON_ICON.codeLocation}>
        {isPath ? t.lesson.tracePath : t.lesson.codeLocation}
      </BlockTitle>
      <ol className="flex flex-col gap-1">
        {anchors.map((a, i) => (
          <li key={`${a.file}-${a.line_start}-${i}`}>
            <button
              onClick={() => onFileClick(a.file, a.line_start, a.line_end)}
              className="group flex w-full items-baseline gap-2.5 rounded-field px-2 py-1 text-start transition hover:bg-slab"
            >
              {isPath && (
                <span className="font-mono text-micro uppercase tracking-[0.13em] text-graphite">
                  {t.lesson.anchorStep(i + 1, anchors.length)}
                </span>
              )}
              <span className="min-w-0 flex-1 truncate font-mono text-micro text-signal transition group-hover:text-chalk">
                {a.symbol ?? a.file}
              </span>
              <span className="shrink-0 font-mono text-micro text-graphite">
                {t.lesson.lines(a.line_start, a.line_end)}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
