import { tagStyle, tagLabel } from "@/lib/tags";

/**
 * One concept-tag chip, in the tag's own fixed hue.
 *
 * Three copies existed, in LessonPanel, MapView and SectionOverview. The colours
 * come from `lib/tags.ts` as CSS variable references and are applied inline
 * rather than as classes, which is deliberate and unchanged: a literal hex in a
 * class would be the one thing on the page a theme could not re-tune.
 *
 * Measured 5.22:1 (free-form) to 8.54:1 (synthesis) on ink and slab, so the tag
 * palette is sound and is not touched here. The four tags that measure 4.2–4.35:1
 * do so only on the map's current-stop card, whose `signal-wash` background is
 * lighter than slab — a surface the palette was never validated against, and a
 * systematic fix that belongs with the visual pass rather than a mechanical
 * extraction.
 */
export default function ConceptTag({ tag }: { tag: string }) {
  const s = tagStyle(tag);
  return (
    <span
      className="rounded-[2px] border px-1.5 py-px font-mono text-micro tracking-[0.05em]"
      style={{ color: s.text, borderColor: s.border, background: s.background }}
    >
      {tagLabel(tag)}
    </span>
  );
}
