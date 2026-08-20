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
export default function SectionLabel({
  children,
  as: Tag = "div",
  tone = "quiet",
}: {
  children: React.ReactNode;
  as?: "div" | "h2" | "h3";
  /**
   * `quiet` is graphite, for a label on the page ground. `raised` is paper, for a
   * label sitting on the practice well: graphite measures 4.05:1 on `raise` in the
   * light theme, just under AA. D3's disabled-token analysis excluded `raise` on
   * the grounds that no control is ever drawn on it — the practice surface made
   * that no longer true, so the exception has to be paid for here.
   */
  tone?: "quiet" | "raised";
}) {
  return (
    <Tag className="flex items-center gap-2.5">
      <span className={`font-mono text-micro uppercase tracking-[0.16em] ${
        tone === "raised" ? "text-paper" : "text-graphite"
      }`}>
        {children}
      </span>
      <span aria-hidden className="h-px flex-1 bg-rule" />
    </Tag>
  );
}
