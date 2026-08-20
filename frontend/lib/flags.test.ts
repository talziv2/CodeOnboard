import { afterEach, describe, expect, test } from "vitest";
import { isPhaseDriven, lessonUi, type LessonUi } from "@/lib/flags";

/**
 * The flag has three values because the decision it gates has been revised once.
 *
 * `next` is not a fallback for `surfaces`; it is what `surfaces` is measured
 * against (S6, against S0's live baseline). The test that matters most is the last
 * one: an unrecognised value must not take the app down.
 */

const set = (value: string | undefined) => {
  if (value === undefined) delete process.env.NEXT_PUBLIC_CODEONBOARD_UI;
  else process.env.NEXT_PUBLIC_CODEONBOARD_UI = value;
};

afterEach(() => set(undefined));

describe("lessonUi", () => {
  test("all three values are reachable", () => {
    set("legacy");
    expect(lessonUi()).toBe("legacy");
    set("next");
    expect(lessonUi()).toBe("next");
    set("surfaces");
    expect(lessonUi()).toBe("surfaces");
  });

  test("unset means legacy — the shipped renderer is the default", () => {
    set(undefined);
    expect(lessonUi()).toBe("legacy");
  });

  test("an unknown value falls back to legacy rather than throwing", () => {
    // A typo in an env var should not take the app down, and it must not silently
    // land on an unproven renderer either.
    for (const junk of ["Next", "SURFACES", "surface", "true", "1", ""]) {
      set(junk);
      expect(lessonUi(), junk).toBe("legacy");
    }
  });
});

describe("isPhaseDriven", () => {
  test("both new arrangements read from the phase model; legacy does not", () => {
    expect(isPhaseDriven("next")).toBe(true);
    expect(isPhaseDriven("surfaces")).toBe(true);
    expect(isPhaseDriven("legacy")).toBe(false);
  });

  test("it is total over the type, so a fourth value cannot be forgotten", () => {
    const all: LessonUi[] = ["legacy", "next", "surfaces"];
    for (const ui of all) expect(typeof isPhaseDriven(ui)).toBe("boolean");
  });
});
