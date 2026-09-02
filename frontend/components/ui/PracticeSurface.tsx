import SectionLabel from "@/components/ui/SectionLabel";

/**
 * The region where the learner is asked something and answers it.
 *
 * This exists because 18px type was not enough. Making the question larger than
 * the prose distinguishes it by degree; being asked to demonstrate understanding
 * is different from reading in *kind*, and a categorical difference wants a
 * categorical signal. So the question gets a surface of its own.
 *
 * The surface is its own token, `well`, chosen by measurement. Against the page,
 * `trench` separates by only 1.02 in dark — invisible — and both `trench` and
 * `slab` manage about 1.09 in light. `raise` reads in both (1.23 / 1.28) but
 * carries mid-grey text at only 4.05:1 in light, because D3 tuned `graphite` and
 * `muted` against ink, trench and slab and deliberately excluded `raise` on the
 * grounds that nothing was ever drawn on it. This surface made that untrue, so it
 * gets a value that satisfies both constraints: see `--color-well` in globals.css.
 * The region a learner acts in is still more distinct from the page than anything
 * merely being shown to them, which is the point.
 *
 * The composer nests on `trench`, a further 1.20 / 1.18 step. The direction flips
 * between themes — the well is lighter than the page in dark and darker in light —
 * which is inherent to a palette that swaps values rather than inverting, and does
 * not matter: what carries is that this is visibly different material.
 *
 * The region PERSISTS across question → answer → feedback. Only its contents
 * change, and the eyebrow changes with them. That is what makes the three read as
 * one interaction rather than three stacked blocks: the feedback arrives where the
 * question was, inside the same frame, instead of appearing a screen further down
 * past the explanation.
 *
 * The two-tab alternative — Lesson and Practice as separate tabs — was considered
 * and rejected for now; see ui-direction.md §13, including what would justify
 * revisiting it.
 */
export default function PracticeSurface({
  label,
  icon,
  children,
}: {
  label: string;
  /**
   * The marker for whichever of the three contents is in the region.
   *
   * It changes with the eyebrow, and for the same reason the eyebrow changes at
   * all: this frame persists across question → answer → feedback, so the label is
   * the only thing that says which of the three the learner is looking at. A
   * fixed glyph here would work against that.
   */
  icon?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4 rounded-panel border border-rule bg-well p-5">
      <SectionLabel tone="raised" icon={icon}>
        {label}
      </SectionLabel>
      {children}
    </section>
  );
}
