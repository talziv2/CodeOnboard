/**
 * A tinted box with a mono eyebrow and a body: the shape the lesson uses to set
 * something apart from the prose around it.
 *
 * Five sites, one shape, three tones. The tones are semantic and unchanged —
 * `signal` for something the system is telling the learner to do or notice
 * (takeaway, hint, follow-up), `jade` for something closed or recovered, and
 * `neutral` for an aside that carries no verdict (ownership).
 *
 * Only the eyebrow and the container are owned here. Bodies differ genuinely —
 * one is a struck-through list of closed gaps, the others are paragraphs at
 * different sizes — so they stay as children rather than becoming props.
 *
 * Not a redesign: `rounded`, `px-4 py-3` and the tint values are exactly what
 * was already there. The visual pass may well give callouts the new radius and a
 * surface rather than a tint; that is not this milestone's call.
 */
type Tone = "signal" | "jade" | "neutral";

const TONE: Record<Tone, { box: string; label: string }> = {
  signal: { box: "border-signal-dim/40 bg-signal/[0.06]", label: "text-signal" },
  jade: { box: "border-jade/40 bg-jade/10", label: "text-jade" },
  neutral: { box: "border-rule bg-slab", label: "text-graphite" },
};

export default function Callout({
  tone,
  label,
  className = "",
  children,
}: {
  tone: Tone;
  label: string;
  /** Layout that belongs to the surrounding flow, not the callout — e.g. `mt-1`. */
  className?: string;
  children: React.ReactNode;
}) {
  const t = TONE[tone];
  return (
    <div className={`flex flex-col gap-1.5 rounded border px-4 py-3 ${t.box} ${className}`}>
      <span
        className={`font-mono text-[calc(9.5rem/16)] uppercase tracking-[0.14em] ${t.label}`}
      >
        {label}
      </span>
      {children}
    </div>
  );
}
