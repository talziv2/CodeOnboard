/**
 * One decorative emoji, beside a label.
 *
 * The whole of the presentation for `lib/lessonIcons.ts`, in one place, because
 * a marker rendered five different sizes in five components is five things to
 * keep in step. Three decisions live here:
 *
 * `aria-hidden`, ALWAYS. A marker adds nothing a screen reader needs — the label
 * beside it is the accessible name — and announcing it would prefix every heading
 * in the lesson with the name of a picture. This is also what keeps the existing
 * tests honest: they query by the copy in `strings.ts`, and a marker that entered
 * the accessible name would change what every one of them is asking for.
 *
 * A SIBLING OF THE LABEL, NEVER ITS PARENT. Every caller renders this next to the
 * text span rather than wrapping it, so the text element's own content is
 * unchanged and `getByText(t.lesson.setup)` still matches exactly what it matched
 * before. Nesting would have appended the glyph to the label's text content and
 * broken the queries silently — the block still renders, the test just stops
 * finding it.
 *
 * BIGGER THAN THE EYEBROW IT SITS ON. The mono labels are 11px, and an emoji at
 * 11px is a smudge; `text-aside` (14px) is legible without out-weighing the
 * label. `leading-none` keeps it off the label's line box, so a marker cannot
 * change the height of the row it decorates.
 *
 * SIZE IS A NAMED PROP AND NOT SOMETHING `className` CAN OVERRIDE. It was: the
 * verdict card passed `className="text-lede"` to sit beside its 18px headline,
 * which put two font-size utilities of EQUAL specificity on one element. Order in
 * the class string is irrelevant to that; the winner is whichever rule Tailwind
 * emits last, which here follows the order the sizes are declared in the `@theme`
 * block. It resolved correctly by luck, and would have inverted silently if
 * anyone reordered the type scale. So the caller names a step and this picks one
 * class.
 *
 * Returns null on an empty glyph, so a caller reading a table that has no entry
 * for its case — an unknown verdict — renders no marker rather than a gap.
 */
const SIZE = {
  /** Beside an 11px mono eyebrow, which is almost everywhere. */
  aside: "text-aside",
  /** Beside the verdict's 18px headline, the one place the type is larger. */
  lede: "text-lede",
} as const;

export default function Marker({
  glyph,
  size = "aside",
  className = "",
}: {
  glyph: string | undefined;
  /** Which step of the type scale the glyph is set at. */
  size?: keyof typeof SIZE;
  /** Layout that belongs to the row, not to the marker — e.g. `mt-px`. Never a
   *  font size; use `size`. */
  className?: string;
}) {
  if (!glyph) return null;
  return (
    <span aria-hidden className={`shrink-0 ${SIZE[size]} leading-none ${className}`}>
      {glyph}
    </span>
  );
}
