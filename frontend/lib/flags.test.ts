import { afterEach, describe, expect, test } from "vitest";
import { isSplitSurfaces, lessonUi, tutorUi, type LessonUi } from "@/lib/flags";

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

/**
 * The Tutor's build-time flag, which now DEFAULTS ON.
 *
 * The bug these pin is not a wrong branch, it is a missing feature. While this
 * read `=== "1"`, a fresh clone with no `.env.local` compiled the CHAT control out
 * of the bundle, with no error and no warning — the Tutor looked unbuilt. And
 * because Next inlines `NEXT_PUBLIC_*` at build time, setting the variable in an
 * already-running dev server changes nothing, so the obvious check for "is the
 * flag on" reports the wrong answer.
 *
 * So the case that matters most is the FIRST one below: unset must be on. The rest
 * exist to keep the escape hatch honest — an explicit `0` still disables, and
 * nothing else does.
 */

const setTutor = (value: string | undefined) => {
  if (value === undefined) delete process.env.NEXT_PUBLIC_CODEONBOARD_TUTOR;
  else process.env.NEXT_PUBLIC_CODEONBOARD_TUTOR = value;
};

describe("tutorUi", () => {
  afterEach(() => setTutor(undefined));

  test("unset means enabled — a fresh clone builds a bundle with the Tutor in it", () => {
    setTutor(undefined);
    expect(tutorUi()).toBe(true);
  });

  test("an explicit `0` still disables it, which is the whole escape hatch", () => {
    setTutor("0");
    expect(tutorUi()).toBe(false);
  });

  test("`1` remains the explicit way to say on", () => {
    setTutor("1");
    expect(tutorUi()).toBe(true);
  });

  test("only `0` disables — a typo must not remove the feature silently", () => {
    for (const junk of ["", " ", "00", "0.0", "false", "off", "no", "junk", "-1"]) {
      setTutor(junk);
      expect(tutorUi(), junk).toBe(true);
    }
  });
});
