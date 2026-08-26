import type { Disposition, UnderstandingClass } from "@/lib/api";
import { standingOf, standingStyle } from "@/lib/standing";

/**
 * The route pin: what the evidence shows about one unit, plus whether the learner
 * is standing on it.
 *
 * Three near-identical copies of this markup existed, in RouteRail, SectionOverview
 * and MapView's journey list. `understandingStyle` was already shared — that part
 * was fixed by M3a.3, after a stop could read amber in the rail and "Needs work" on
 * the map — but the twenty lines wrapping it were not, which is how the three drifted
 * apart in every dimension the encoding does not cover.
 *
 * Those differences are PRESERVED here, not reconciled:
 *
 *   role      size   border   halo   inner dot
 *   rail      17px   1.5px    3px    yes, inset 3.5px
 *   map       15px   2px      4px    yes, inset 3px
 *   list      13px   1.5px    3px    NO
 *
 * The rail's pin being larger than the map's, two border widths, two halo widths,
 * and the chapter overview alone omitting the filled centre that marks the current
 * stop all look like drift rather than intent. Deciding that is a visual question,
 * so it belongs to the pass that owns geometry — this milestone only stops the
 * markup being written out three times. Sizes are named by role rather than by
 * s/m/l precisely so that reconciling them later is a change of values in one table
 * and not a hunt through three files.
 *
 * MapView's `Pip` and EvidenceDrawer's inline dot are deliberately not folded in:
 * one is a button with its own hover behaviour, the other sits inside a text row,
 * both are half a dozen lines, and both already read the shared encoding.
 *
 * ── The settled bar ───────────────────────────────────────────────────────────
 *
 * A pin may carry a bar across it, meaning **the learner closed this question
 * without demonstrating it** — moved on, waived it, skipped it, asserted they
 * already knew it, or walked past without answering at all. The colour still says what the evidence shows; the bar says a
 * decision was taken over the top of it. Two claims, two channels, so neither
 * overwrites the other — which is the whole reason understanding and disposition
 * are separate dimensions server-side.
 *
 * Shape rather than hue, like the dash, and for the same accessibility reason:
 * without it a stop the learner deliberately set aside and one they are still
 * stuck on are the same circle.
 */
type PinRole = "rail" | "map" | "list";

const ROLE: Record<
  PinRole,
  { box: string; border: string; halo: string; dot: string | null }
> = {
  // `relative` only where the original had it: it is what the inner dot is
  // positioned against, and the list role has no dot to position.
  rail: {
    box: "relative h-[calc(17rem/16)] w-[calc(17rem/16)]",
    border: "border-[1.5px]",
    halo: "0 0 0 3px var(--color-signal-halo)",
    dot: "inset-[calc(3.5rem/16)]",
  },
  map: {
    box: "relative h-[calc(15rem/16)] w-[calc(15rem/16)]",
    border: "border-2",
    halo: "0 0 0 4px var(--color-signal-halo)",
    dot: "inset-[calc(3rem/16)]",
  },
  list: {
    box: "h-[calc(13rem/16)] w-[calc(13rem/16)]",
    border: "border-[1.5px]",
    halo: "0 0 0 3px var(--color-signal-halo)",
    dot: null,
  },
};

export default function StatePin({
  understanding,
  disposition,
  attempted,
  visited,
  isCurrent,
  role,
  className = "",
}: {
  understanding: UnderstandingClass | undefined;
  /** What the learner DECIDED here. Omit where the caller has no node. */
  disposition?: Disposition;
  /** Have they answered this stop's own question? Omit where unknown. */
  attempted?: boolean;
  /** Have they walked PAST it? What separates a skipped stop from an unopened one. */
  visited?: boolean;
  isCurrent: boolean;
  role: PinRole;
  /** Positioning that belongs to the row, not the pin — margins, z-index. */
  className?: string;
}) {
  const standing = standingOf({ understanding, disposition, attempted, visited });
  const style = standingStyle(standing, understanding);
  const r = ROLE[role];
  return (
    <span
      aria-hidden
      // `relative` unconditionally once a bar can be drawn: the list role had no
      // inner dot to position against and therefore no positioning context, and
      // a bar without one escapes to the nearest ancestor that has.
      className={`relative shrink-0 rounded-full bg-ink ${r.box} ${r.border} ${className}`}
      style={{
        borderColor: isCurrent ? "var(--color-signal)" : style.stroke,
        borderStyle: style.borderStyle,
        background: isCurrent ? "var(--color-ink)" : style.fill,
        boxShadow: isCurrent ? r.halo : undefined,
      }}
    >
      {isCurrent && r.dot && (
        <span className={`absolute ${r.dot} rounded-full bg-signal`} />
      )}
      {/* Drawn even on the current stop. Standing on a stop does not undo the
          decision taken there, and the signal ring already says "you are here"
          in a channel this does not touch. Inset so it reads as a bar across the
          pin rather than a line through the row. */}
      {style.settled && (
        <span
          className="absolute inset-x-[15%] top-1/2 h-px -translate-y-1/2"
          style={{ background: isCurrent ? "var(--color-signal)" : style.stroke }}
        />
      )}
    </span>
  );
}
