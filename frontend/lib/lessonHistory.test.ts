import { describe, expect, test } from "vitest";
import type { Attempt } from "@/lib/api";
import { materialIsNew, supersededExplanations } from "@/lib/lessonHistory";

/**
 * R3's third mitigation, as a pure function.
 *
 * The claim being protected: Lesson stays exactly one expanded section long no
 * matter how many times a stop has been re-taught. What makes that safe rather than
 * lossy is that the replaced versions are still reachable — so the thing to test is
 * that they are found, ordered, attributed to the answer that replaced them, and
 * that nothing empty is ever offered.
 */

const attempt = (over: Partial<Attempt> = {}): Attempt => ({
  answer: "An answer.",
  classification: "confused",
  rationale: "Because.",
  at: "2026-08-20T10:00:00+00:00",
  ...over,
});

const retaught = (setup: string, answer: string, at = "2026-08-20T10:00:00+00:00"): Attempt =>
  attempt({
    answer,
    at,
    response: {
      action: "reteach",
      retaught: true,
      superseded_lesson: { setup, reveal: `${setup} — explained.` },
      at,
    },
  });

describe("finding the versions a re-teach replaced", () => {
  test("none, for a stop that was never re-taught", () => {
    expect(supersededExplanations([attempt(), attempt()])).toEqual([]);
  });

  test("one per re-teach, oldest first, numbered from the first version seen", () => {
    const versions = supersededExplanations([
      retaught("The first prose.", "First wrong answer.", "2026-08-20T10:00:00+00:00"),
      attempt(),
      retaught("The second prose.", "Second wrong answer.", "2026-08-20T11:00:00+00:00"),
    ]);
    expect(versions.map((v) => v.version)).toEqual([1, 2]);
    expect(versions[0].setup).toBe("The first prose.");
    expect(versions[1].setup).toBe("The second prose.");
  });

  test("each version names the answer that replaced it", () => {
    // What makes this a record rather than a pile. "Version 1, replaced after you
    // answered X" is a sentence about the learner.
    const [first] = supersededExplanations([retaught("Prose.", "My wrong answer.")]);
    expect(first.answer).toBe("My wrong answer.");
  });

  test("a re-teach that failed replaced nothing, so it offers nothing", () => {
    const failed = attempt({ response: { action: "reteach", retaught: false } });
    expect(supersededExplanations([failed])).toEqual([]);
  });

  test("a hint never touched the prose", () => {
    const hint = attempt({ response: { action: "hint", text: "Look at h()." } });
    expect(supersededExplanations([hint])).toEqual([]);
  });

  test("an entry with nothing readable behind it is dropped", () => {
    // A disclosure that opens on emptiness is worse than one fewer entry.
    const hollow = attempt({
      response: { action: "reteach", retaught: true, superseded_lesson: {} },
    });
    expect(supersededExplanations([hollow])).toEqual([]);
  });

  test("pre-B4 records fall back to the walkthrough", () => {
    const old = attempt({
      response: {
        action: "reteach",
        retaught: true,
        superseded_lesson: { walkthrough: "One body, no split." },
      },
    });
    expect(supersededExplanations([old])[0].setup).toBe("One body, no split.");
  });

  test("verification attempts are excluded, not merely absent", () => {
    // A verification never re-teaches. Pooling it here would put an entry in the
    // list with no explanation behind it.
    const check = attempt({
      kind: "verification",
      response: {
        action: "reteach",
        retaught: true,
        superseded_lesson: { setup: "Should not appear." },
      },
    });
    expect(supersededExplanations([check])).toEqual([]);
  });
});

describe("whether the material on screen is new", () => {
  test("true when the last answer rewrote it", () => {
    expect(materialIsNew([attempt(), retaught("Prose.", "Wrong.")])).toBe(true);
  });

  test("false when an earlier answer rewrote it but the last one did not", () => {
    // An earlier re-teach is not news; its output is what the learner has been
    // reading since.
    expect(materialIsNew([retaught("Prose.", "Wrong."), attempt()])).toBe(false);
  });

  test("false for a stop with no attempts at all", () => {
    expect(materialIsNew([])).toBe(false);
  });

  test("a verification after a re-teach does not make the re-teach stale news", () => {
    // Verifications are not assessments, so they do not take the "last answer"
    // slot. The prose is still the prose the last ASSESSMENT produced.
    const check = attempt({ kind: "verification" });
    expect(materialIsNew([retaught("Prose.", "Wrong."), check])).toBe(true);
  });
});
