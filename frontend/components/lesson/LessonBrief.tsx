"use client";

import type { GraphNode } from "@/lib/api";
import ConceptTag from "@/components/ui/ConceptTag";
import { t } from "@/lib/strings";

/**
 * Which stop this is, what it is for, and what is outstanding on it.
 *
 * This is the part of the lesson that has to survive scrolling, which is why it
 * is what `LessonWorkspace` pins. So it carries the four things a learner needs
 * while reading anything further down:
 *
 *   position    where they are on the walk (or that this is a warm-up)
 *   title       what the stop is
 *   objective   the claim they should be able to make afterwards — the contract
 *               between the Planner, Teaching and the Grader, and the standard
 *               their answer is actually marked against. It scrolled away first
 *               before this, being at the very top of a long column.
 *   counters    what is still open and how many answers exist
 *
 * The counters are TRIGGERS, not replacements. The gap list and the attempt
 * history are still inline exactly where they were; these take you to them. L4 is
 * where that changes — §3a asks whether gaps should collapse to a counter the
 * moment a verdict lands, and whether the history is ever wanted during feedback
 * — and keeping both for now means the answer can be wrong without losing
 * anything.
 *
 * Anchors are listed compactly rather than as the single display file. A unit
 * grounded in three places has three, and `TracePath` below is still the ordered
 * walk through them; this is the "where does this live" answer, which a learner
 * wants without scrolling back.
 */
export default function LessonBrief({
  node,
  position,
  total,
  isPrerequisite,
  onFileClick,
  openGapCount = 0,
  attemptCount = 0,
  onShowGaps,
  onShowAttempts,
}: {
  node: GraphNode;
  position: number;
  total: number;
  isPrerequisite: boolean;
  onFileClick: (file: string, lineStart?: number, lineEnd?: number) => void;
  openGapCount?: number;
  attemptCount?: number;
  onShowGaps?: () => void;
  onShowAttempts?: () => void;
}) {
  const anchors = node.anchors ?? [];
  // One anchor is the display anchor, which the title line already accounts for;
  // listing it twice would be noise. Two or more is a real set.
  const showAnchorList = anchors.length > 1;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
          {isPrerequisite ? t.lesson.warmUpHeading : t.lesson.stopOf(position, total)}
        </span>

        {/* Counters sit on the position line, not under the title: they are
            status, and the title is the subject. */}
        <span className="ms-auto flex items-center gap-2">
          {openGapCount > 0 && (
            <button
              onClick={onShowGaps}
              className="font-mono text-micro text-rust transition hover:text-chalk"
            >
              {t.lesson.briefGaps(openGapCount)}
            </button>
          )}
          {attemptCount > 0 && (
            <button
              onClick={onShowAttempts}
              className="font-mono text-micro text-graphite transition hover:text-signal"
            >
              {t.lesson.briefAttempts(attemptCount)}
            </button>
          )}
        </span>
      </div>

      <h2 className="font-display text-head font-medium tracking-tight text-chalk text-balance">
        {node.title}
      </h2>

      {node.objective && (
        // Clamped to two lines. The brief is pinned, so it spends viewport that
        // the lesson needs — and at the `xlarge` text size an unclamped objective
        // is what would eat it.
        <p className="measure line-clamp-2 text-meta text-paper">{node.objective}</p>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <button
          onClick={() => onFileClick(node.file)}
          className="w-fit border-b border-dashed border-signal-dim pb-px font-mono text-micro text-signal transition hover:border-signal"
        >
          {node.file}
          {" · "}
          {t.lesson.lines(node.line_start, node.line_end)}
        </button>

        {showAnchorList &&
          anchors.slice(1).map((a, i) => (
            <button
              key={`${a.file}-${a.line_start}-${i}`}
              onClick={() => onFileClick(a.file, a.line_start, a.line_end)}
              className="w-fit border-b border-dashed border-rule pb-px font-mono text-micro text-graphite transition hover:border-signal-dim hover:text-signal"
            >
              {a.symbol ?? a.file}
            </button>
          ))}
      </div>

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
