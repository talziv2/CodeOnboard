import { afterEach, describe, expect, test } from "vitest";
import { isSplitSurfaces, lessonUi, type LessonUi } from "@/lib/flags";

/**
 * Two values now, and the default is the redesign.
 *
 * Before L5 there were three and an unset variable meant the pre-redesign
 * renderer, so the whole redesign was opt-in. `legacy` is deleted and the default
 * inverted: the flag now exists to opt OUT of the split, and the test that matters
 * most is the last one — an unrecognised value must land somewhere sane, and
 * "somewhere sane" is only true while the default is the thing we believe is best.
 */

const set = (value: string | undefined) => {
  if (value === undefined) delete process.env.NEXT_PUBLIC_CODEONBOARD_UI;
  else process.env.NEXT_PUBLIC_CODEONBOARD_UI = value;
};

afterEach(() => set(undefined));

describe("lessonUi", () => {
  test("both values are reachable", () => {
    set("surfaces");
    expect(lessonUi()).toBe("surfaces");
    set("next");
    expect(lessonUi()).toBe("next");
  });

  test("unset means surfaces — the redesign is the default now", () => {
    set(undefined);
    expect(lessonUi()).toBe("surfaces");
  });

  test("`legacy` is gone, and asking for it does not resurrect it", () => {
    // The renderer is deleted, so the old value must not silently select
    // something else surprising. It falls back like any other unknown string.
    set("legacy");
    expect(lessonUi()).toBe("surfaces");
  });

  test("an unknown value falls back to the default rather than throwing", () => {
    for (const junk of ["Next", "SURFACES", "surface", "true", "1", ""]) {
      set(junk);
      expect(lessonUi(), junk).toBe("surfaces");
    }
  });
});

describe("isSplitSurfaces", () => {
  test("only `surfaces` draws one surface at a time", () => {
    expect(isSplitSurfaces("surfaces")).toBe(true);
    expect(isSplitSurfaces("next")).toBe(false);
  });

  test("it is total over the type", () => {
    const all: LessonUi[] = ["next", "surfaces"];
    for (const ui of all) expect(typeof isSplitSurfaces(ui)).toBe("boolean");
  });
});
