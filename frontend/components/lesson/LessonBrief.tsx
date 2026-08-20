"use client";

import type { GraphNode } from "@/lib/api";
import ConceptTag from "@/components/ui/ConceptTag";
import { t } from "@/lib/strings";

/**
 * Which stop this is, what it is called, and where it lives.
 *
 * Moved out of `LessonPanel` unchanged — same markup, same order. L3 is where
 * this becomes the sticky frame the canvas scrolls beneath; extracting it first
 * means that change has one place to happen.
 */
export default function LessonBrief({
  node,
  position,
  total,
  isPrerequisite,
  onFileClick,
}: {
  node: GraphNode;
  position: number;
  total: number;
  isPrerequisite: boolean;
  onFileClick: (file: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
        {isPrerequisite ? t.lesson.warmUpHeading : t.lesson.stopOf(position, total)}
      </span>

      <h2 className="font-display text-head font-medium tracking-tight text-chalk text-balance">
        {node.title}
      </h2>

      <button
        onClick={() => onFileClick(node.file)}
        className="w-fit border-b border-dashed border-signal-dim pb-px font-mono text-micro text-signal transition hover:border-signal"
      >
        {node.file}
        {" · "}
        {t.lesson.lines(node.line_start, node.line_end)}
      </button>

      {node.concept_tags.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {node.concept_tags.map((tag) => (
            <ConceptTag key={tag} tag={tag} />
          ))}
        </div>
      )}
    </div>
  );
}
