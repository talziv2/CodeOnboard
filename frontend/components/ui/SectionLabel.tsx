"use client";

import { createContext, useContext, type ReactNode } from "react";
import Marker from "@/components/ui/Marker";

/**
 * The mono eyebrow above a block, with a hairline rule filling the row.
 *
 * Five byte-identical copies of this existed — one exported from LessonPanel and
 * four written out inline in SectionOverview (×2), MapView and the welcome page.
 * Extracted at exactly the current values; nothing about how it looks changes here.
 *
 * `as` exists because MapView's copy is an `h3` and that is correct: it labels the
 * journey section, which is a real heading. The others label blocks inside a page
 * that already has its heading, so `div` is right for them.
 */

type Props = {
  children: ReactNode;
  as?: "div" | "h2" | "h3";
  /**
   * A decorative marker from `lib/lessonIcons.ts`, before the label.
   *
   * Optional, and absent everywhere outside the lesson: the markers exist to
   * tell one lesson block from the next, and the map, the rail and the dashboard
   * do not have that problem. Rendered as a SIBLING of the label span, so the
   * label's own text content is unchanged — see `Marker`.
   */
  icon?: string;
  /**
   * `quiet` is graphite, for a label on the page ground. `raised` is paper, for a
   * label sitting on the practice well: graphite measures 4.05:1 on `raise` in the
   * light theme, just under AA. D3's disabled-token analysis excluded `raise` on
   * the grounds that no control is ever drawn on it — the practice surface made
   * that no longer true, so the exception has to be paid for here.
   */
  tone?: "quiet" | "raised";
};

export default function SectionLabel({
  children,
  as: Tag = "div",
  tone = "quiet",
  icon,
}: Props) {
  return (
    <Tag className="flex items-center gap-2.5">
      <Marker glyph={icon} />
      <span className={`font-mono text-micro uppercase tracking-[0.16em] ${
        tone === "raised" ? "text-paper" : "text-graphite"
      }`}>
        {children}
      </span>
      <span aria-hidden className="h-px flex-1 bg-rule" />
    </Tag>
  );
}

/**
 * "An ancestor already displays this block's name."
 *
 * ── The defect ────────────────────────────────────────────────────────────────
 *
 * A block that `LessonCanvas` renders as a `Disclosure` was named TWICE: once on
 * the summary row, which is the disclosure's whole job, and again by the block's
 * own eyebrow immediately under it. So opening the code path showed
 * `THIS PATH CROSSES SEVERAL PLACES` and then, one line down,
 * `THIS PATH CROSSES SEVERAL PLACES` — and the answer log showed
 * `YOUR ANSWERS (1)` above `YOUR ANSWERS (1)`.
 *
 * It had always been there and was easy not to see, because two identical runs of
 * 11px uppercase grey read as one texture. Giving each block a marker is what made
 * it obvious: the same glyph twice, four pixels apart, is not a texture.
 *
 * ── Why a context and not a prop ─────────────────────────────────────────────
 *
 * The two halves of this fact are held by two components that do not meet. The
 * DISCLOSURE knows it has already displayed the name; the block's TITLE knows
 * which of its labels is the name (`GapList` also renders `Settled`, which is a
 * real sub-heading and must survive). Nobody in between knows both.
 *
 * The tempting prop — `heading={false}` from `LessonPanel` — cannot be written
 * honestly, because `LessonPanel` does not know whether a block will be collapsed:
 * `LessonCanvas` decides that from `surfaceBlocks`, and `surfaceBlocks` applies the
 * surface's own supersession. Passing the prop would mean deriving "is this block
 * collapsed" a second time, in a second place, from a different input — which is
 * the exact shape of defect this layer was restructured to remove, and the reason
 * `frontend/CLAUDE.md` says not to derive a fact twice.
 *
 * So the disclosure states the fact once, where it is known, and the title reads
 * it. Nothing is computed anywhere.
 *
 * Default `false`, so a block rendered bare — the expanded case, and every use
 * outside the lesson — is unaffected and keeps its eyebrow.
 */
const AlreadyNamedContext = createContext(false);

/** Wraps a disclosure's contents. See `AlreadyNamedContext`. */
export function AlreadyNamed({ children }: { children: ReactNode }) {
  return (
    <AlreadyNamedContext.Provider value={true}>{children}</AlreadyNamedContext.Provider>
  );
}

/**
 * A block's OWN title — the label that names the whole block.
 *
 * Identical to `SectionLabel`, except that it renders nothing when an ancestor has
 * already displayed the name. Use it for the one label at the top of a block, and
 * plain `SectionLabel` for a sub-heading inside one: `GapList`'s `Settled` is a
 * `SectionLabel`, because a disclosure summary reading "what you got wrong here"
 * has not named it and hiding it would lose a real division.
 */
export function BlockTitle(props: Props) {
  const namedAbove = useContext(AlreadyNamedContext);
  if (namedAbove) return null;
  return <SectionLabel {...props} />;
}
