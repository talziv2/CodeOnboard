import Marker from "@/components/ui/Marker";

/**
 * A tinted box with a mono eyebrow and a body: the shape the lesson uses to set
 * something apart from the prose around it.
 *
 * Five sites, one shape, four tones. The tones are semantic — `signal` for
 * something the system is telling the learner to do or notice (takeaway, hint,
 * follow-up), `jade` for something closed or recovered, `brass` for something
 * unsettled that wants attention without being an error, and `neutral` for an
 * aside that carries no verdict (ownership).
 *
 * `brass` is the palette's yellow, and it already means exactly this elsewhere —
 * a `partial` verdict, `checkOpen`, a failed grade. The arrival notice borrows it
 * for the same reason: being off the route is not a failure and not a warning,
 * but it is the one thing on the page the learner should notice before reading
 * the lesson under it. Weighted toward the BORDER rather than the fill, so it
 * marks the box without turning it into a warning banner.
 *
 * Only the eyebrow and the container are owned here. Bodies differ genuinely —
 * one is a struck-through list of closed gaps, the others are paragraphs at
 * different sizes — so they stay as children rather than becoming props.
 *
 * Not a redesign: `rounded`, `px-4 py-3` and the tint values are exactly what
 * was already there. The visual pass may well give callouts the new radius and a
 * surface rather than a tint; that is not this milestone's call.
 */
type Tone = "signal" | "jade" | "brass" | "neutral";

const TONE: Record<Tone, { box: string; label: string }> = {
  signal: { box: "border-signal-dim/40 bg-signal/[0.06]", label: "text-signal" },
  jade: { box: "border-jade/40 bg-jade/10", label: "text-jade" },
  // A more definite border than the others and a fainter wash, because this tone
  // exists to outline rather than to fill.
  brass: { box: "border-brass/60 bg-brass/[0.07]", label: "text-brass" },
  neutral: { box: "border-rule bg-slab", label: "text-graphite" },
};

export default function Callout({
  tone,
  label,
  className = "",
  icon,
  children,
}: {
  tone: Tone;
  label: string;
  /**
   * A decorative marker from `lib/lessonIcons.ts`, before the eyebrow.
   *
   * The eyebrow already carries the tone's colour, and the marker is the second
   * half of the same job on a screen where four of these can be stacked: the
   * takeaway, the hint and the arrival notice are three different kinds of aside
   * and the tone alone distinguishes only three of the four.
   */
  icon?: string;
  /** Layout that belongs to the surrounding flow, not the callout — e.g. `mt-1`. */
  className?: string;
  children: React.ReactNode;
}) {
  const t = TONE[tone];
  return (
    <div className={`flex flex-col gap-1.5 rounded-card border px-4 py-3 ${t.box} ${className}`}>
      <span className="flex items-center gap-2">
        <Marker glyph={icon} />
        <span
          className={`font-mono text-micro uppercase tracking-[0.14em] ${t.label}`}
        >
          {label}
        </span>
      </span>
      {children}
    </div>
  );
}
