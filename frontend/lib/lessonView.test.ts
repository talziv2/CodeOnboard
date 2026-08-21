import { describe, expect, test } from "vitest";
import { lessonBlocks, openCount, type ViewInput } from "@/lib/lessonView";

/**
 * §3a, as assertions.
 *
 * The complaint was that the feedback state is too busy; the count behind it was
 * the verdict card plus five other open blocks around it. So the tests that matter
 * here are about HOW MANY things are open at once and WHICH, not about styling —
 * which is the whole point of answering it as information architecture.
 */

const base: ViewInput = {
  phase: "STUDY",
  locationCount: 3,
  openGapCount: 2,
  attemptCount: 3,
  revealed: true,
  hasReveal: true,
};

describe("what is open in each phase", () => {
  test("STUDY: reading and answering, with the gaps that inform the answer", () => {
    const b = lessonBlocks({ ...base, phase: "STUDY" });

    expect(b.setup).toBe("open");
    // A list of links, and the brief already names the anchors: a disclosure in
    // every phase rather than a fourth place to read where this unit lives.
    expect(b.tracePath).toBe("collapsed");
    expect(b.gaps).toBe("open");
    expect(b.question).toBe("open");
    expect(b.feedback).toBe("absent");
    // A record, never open.
    expect(b.attempts).toBe("collapsed");
  });

  test("FEEDBACK: the verdict, and what it superseded is collapsed", () => {
    const b = lessonBlocks({ ...base, phase: "FEEDBACK" });

    expect(b.feedback).toBe("open");
    expect(b.reveal).toBe("open");
    // The blocks that used to crowd the verdict.
    expect(b.setup).toBe("collapsed");
    expect(b.tracePath).toBe("collapsed");
    expect(b.gaps).toBe("collapsed");
    expect(b.attempts).toBe("collapsed");
    // And the composer is gone, because this phase does not own a question.
    expect(b.question).toBe("absent");
  });

  test("VERIFY: a question again, and the verdict is gone rather than stacked", () => {
    const b = lessonBlocks({ ...base, phase: "VERIFY" });

    expect(b.question).toBe("open");
    expect(b.feedback).toBe("absent");
    // The setup does not re-open: the learner is being re-asked, not re-taught.
    expect(b.setup).toBe("collapsed");
  });

  test("RESOLVED: reports like FEEDBACK, not like a fresh question", () => {
    const b = lessonBlocks({ ...base, phase: "RESOLVED" });

    expect(b.feedback).toBe("open");
    expect(b.question).toBe("absent");
    expect(b.setup).toBe("collapsed");
  });
});

describe("the count §3a was about", () => {
  test("no phase has more than four blocks open at once", () => {
    for (const phase of ["STUDY", "FEEDBACK", "VERIFY", "RESOLVED"] as const) {
      const n = openCount(lessonBlocks({ ...base, phase }));
      expect(n, `${phase} has ${n} open`).toBeLessThanOrEqual(4);
    }
  });

  test("FEEDBACK is the verdict and the explanation, and nothing else", () => {
    const b = lessonBlocks({ ...base, phase: "FEEDBACK" });
    const open = Object.entries(b)
      .filter(([, s]) => s === "open")
      .map(([k]) => k)
      .sort();

    expect(open).toEqual(["feedback", "reveal"]);
  });

  test("exactly one of question and feedback is ever open", () => {
    for (const phase of ["STUDY", "FEEDBACK", "VERIFY", "RESOLVED"] as const) {
      const b = lessonBlocks({ ...base, phase });
      const both = [b.question, b.feedback].filter((s) => s === "open").length;
      // The single-composer invariant, restated structurally: one artifact owns
      // the interaction at a time.
      expect(both, `${phase} has ${both}`).toBe(1);
    }
  });
});

describe("blocks that have nothing to show are absent, not empty", () => {
  test("a unit with no file at all has no code-locations block", () => {
    expect(lessonBlocks({ ...base, locationCount: 0 }).tracePath).toBe("absent");
  });

  test("ONE location still shows — absent used to swallow almost every unit", () => {
    // The old rule was `!multiAnchor ? "absent"`, so the block appeared only on
    // multi-anchor units. Most units have one anchor, or none and only the display
    // projection, so in practice "where does this live in the code" never rendered.
    expect(lessonBlocks({ ...base, locationCount: 1 }).tracePath).toBe("collapsed");
  });

  test("a disclosure in every phase, because open would cost the block budget", () => {
    for (const phase of ["STUDY", "FEEDBACK", "VERIFY", "RESOLVED"] as const) {
      expect(lessonBlocks({ ...base, locationCount: 2, phase }).tracePath).toBe("collapsed");
    }
  });

  test("no gaps means no gap block, in any phase", () => {
    for (const phase of ["STUDY", "FEEDBACK", "VERIFY", "RESOLVED"] as const) {
      expect(
        lessonBlocks({ ...base, phase, openGapCount: 0, gapCount: 0 }).gaps
      ).toBe("absent");
    }
  });

  // The ledger's whole point: clearing the last gap must not delete the record
  // of having cleared it. Absent is reserved for a stop that never had one.
  test("a fully settled ledger stays, collapsed, in every phase", () => {
    for (const phase of ["STUDY", "FEEDBACK", "VERIFY", "RESOLVED"] as const) {
      expect(
        lessonBlocks({ ...base, phase, openGapCount: 0, gapCount: 3 }).gaps
      ).toBe("collapsed");
    }
  });

  test("outstanding gaps still open the block while studying", () => {
    expect(
      lessonBlocks({ ...base, phase: "STUDY", openGapCount: 1, gapCount: 3 }).gaps
    ).toBe("open");
  });

  // Every caller predating the ledger passes only the open count.
  test("without a total, the open count decides existence as it always did", () => {
    expect(lessonBlocks({ ...base, phase: "STUDY", openGapCount: 0 }).gaps).toBe("absent");
    expect(lessonBlocks({ ...base, phase: "STUDY", openGapCount: 2 }).gaps).toBe("open");
  });

  test("a first attempt has no history to collapse", () => {
    expect(lessonBlocks({ ...base, attemptCount: 0 }).attempts).toBe("absent");
  });
});

describe("the reveal is earned, and stays earned", () => {
  test("withheld until an answer exists", () => {
    expect(lessonBlocks({ ...base, phase: "STUDY", revealed: false }).reveal).toBe("absent");
  });

  test("open on a revisit, where the learner is reading rather than being tested", () => {
    // A revisit is STUDY with attempts and no result — the phase model's own case.
    const b = lessonBlocks({ ...base, phase: "STUDY", revealed: true, attemptCount: 2 });
    expect(b.reveal).toBe("open");
    expect(b.question).toBe("open");
  });

  test("a lesson with nothing withheld has no reveal to open", () => {
    expect(lessonBlocks({ ...base, hasReveal: false, revealed: true }).reveal).toBe("absent");
  });

  test("still open while a verification is outstanding", () => {
    // Re-hiding it would be pointless: it has already been read.
    expect(lessonBlocks({ ...base, phase: "VERIFY" }).reveal).toBe("open");
  });
});
