import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import Callout from "@/components/ui/Callout";
import Disclosure from "@/components/ui/Disclosure";
import Marker from "@/components/ui/Marker";
import SectionLabel from "@/components/ui/SectionLabel";
import { BLOCK_ICON, LESSON_ICON, VERDICT_ICON } from "@/lib/lessonIcons";
import { t } from "@/lib/strings";

/**
 * The lesson's emoji markers, and the one property they must never lose.
 *
 * A MARKER IS INVISIBLE TO THE ACCESSIBLE NAME AND TO A TEXT QUERY. That is what
 * makes it decoration rather than copy, and it is the assertion worth a test
 * because the failure mode is silent in both directions at once: nest the glyph
 * inside a label instead of beside it and the block still renders correctly, a
 * screen reader starts announcing "open book, before you answer", and every one
 * of the suite's `getByText(t.lesson.…)` queries quietly starts asking for a
 * string that no longer exists. Nothing looks wrong on the page.
 *
 * So each shell is rendered WITH a marker and the label is queried by its exact
 * copy from `strings.ts` — the same query the rest of the suite makes.
 */

describe("Marker", () => {
  test("renders nothing at all for an absent glyph", () => {
    // The verdict table's own rule: an unknown classification gets no marker,
    // rather than a placeholder standing in for one.
    const { container } = render(<Marker glyph={VERDICT_ICON["a-verdict-we-do-not-know"]} />);
    expect(container.innerHTML).toBe("");
  });

  test("is hidden from assistive technology", () => {
    const { container } = render(<Marker glyph={LESSON_ICON.takeaway} />);
    const span = container.querySelector("span");
    expect(span?.getAttribute("aria-hidden")).toBe("true");
    expect(span?.textContent).toBe(LESSON_ICON.takeaway);
  });
});

describe("a marker never becomes part of its label", () => {
  test("SectionLabel: the copy is still found by its exact text", () => {
    render(<SectionLabel icon={BLOCK_ICON.setup}>{t.lesson.setup}</SectionLabel>);
    const label = screen.getByText(t.lesson.setup);
    expect(label.textContent).toBe(t.lesson.setup);
    expect(label.textContent).not.toContain(BLOCK_ICON.setup);
  });

  test("Callout: the eyebrow is still found by its exact text", () => {
    render(
      <Callout tone="signal" label={t.lesson.takeaway} icon={LESSON_ICON.takeaway}>
        <p>body</p>
      </Callout>
    );
    const label = screen.getByText(t.lesson.takeaway);
    expect(label.textContent).toBe(t.lesson.takeaway);
  });

  test("Disclosure: the summary label is still found by its exact text", () => {
    render(
      <Disclosure label={t.lesson.gapsHeading} icon={BLOCK_ICON.gaps}>
        <p>body</p>
      </Disclosure>
    );
    const label = screen.getByText(t.lesson.gapsHeading);
    expect(label.textContent).toBe(t.lesson.gapsHeading);
  });
});

describe("the table itself", () => {
  test("every marker is a real glyph", () => {
    const all = [
      ...Object.values(BLOCK_ICON),
      ...Object.values(LESSON_ICON),
      ...Object.values(VERDICT_ICON),
    ];
    expect(all.length).toBeGreaterThan(0);
    for (const glyph of all) {
      expect(glyph.trim()).not.toBe("");
      // Two code points at most — a base glyph plus a variation selector. Longer
      // means a ZWJ sequence, which renders as separate glyphs wherever the font
      // has no composed form, and an eyebrow is the wrong place to find out.
      expect([...glyph].length).toBeLessThanOrEqual(2);
    }
  });

  test("the two navigation roles do not share a glyph", () => {
    // The one collision `lessonIcons` had to resolve. Both roles mean "look over
    // here", so one compass serving both would say nothing — and the wording
    // rule for the arrival notice forbids borrowing a warning glyph instead.
    expect(LESSON_ICON.hint).not.toBe(LESSON_ICON.offRoute);
    expect(LESSON_ICON.offRoute).not.toBe(BLOCK_ICON.gaps);
  });

  test("ignored is not resolved, in the glyph channel too", () => {
    // `GapList` holds this distinction in four channels: the wording, the colour,
    // the note underneath, and now the marker. A second tick here would collapse
    // the one thing the ledger exists to keep apart.
    expect(LESSON_ICON.gapWaived).not.toBe(LESSON_ICON.gapResolved);
    expect(LESSON_ICON.gapResolved).toBe(VERDICT_ICON.understood);
  });
});
