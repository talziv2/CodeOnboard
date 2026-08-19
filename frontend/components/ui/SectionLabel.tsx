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
}: {
  children: React.ReactNode;
  as?: "div" | "h2" | "h3";
}) {
  return (
    <Tag className="flex items-center gap-2.5">
      <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.16em] text-graphite">
        {children}
      </span>
      <span aria-hidden className="h-px flex-1 bg-rule" />
    </Tag>
  );
}
