import { describe, expect, test } from "vitest";
import type { LessonPhase } from "@/lib/lessonPhase";
import { lessonBlocks, openCount, type LessonBlocks, type ViewInput } from "@/lib/lessonView";
import {
  MIRRORED,
  SURFACE_OF,
  liveArtifacts,
  openCountIn,
  surfaceBlocks,
  surfaceOf,
  type BlockName,
  type Surface,
} from "@/lib/lessonSurfaces";

/**
 * The surface split, phase by phase and surface by surface.
 *
 * Two claims are worth more than the rest, because they are the risks the design
 * document commits to and the ones a later edit would break silently:
 *
 *   R2 · never nest the two axes for the CURRENT thing. Behind a tab and behind a
 *        disclosure compounds to "where is anything?".
 *   R3 · Lesson never has more than two sections expanded, whatever the adaptation
 *        history — the user's own warning about an accumulating document.
 *
 * Both are asserted over every phase and every plausible combination below, rather
 * than on one example each, because that is the difference between a gate and an
 * illustration.
 */

const PHASES: LessonPhase[] = ["STUDY", "FEEDBACK", "VERIFY", "RESOLVED"];
const SURFACES: Surface[] = ["lesson", "understanding"];

/** Every input combination the view model distinguishes. */
const every: ViewInput[] = [];
for (const phase of PHASES) {
  for (const multiAnchor of [true, false]) {
    for (const openGapCount of [0, 2]) {
      for (const attemptCount of [0, 3]) {
        for (const revealed of [true, false]) {
          for (const hasReveal of [true, false]) {
            every.push({ phase, multiAnchor, openGapCount, attemptCount, revealed, hasReveal });
          }
        }
      }
    }
  }
}

const blocksFor = (input: ViewInput) => lessonBlocks(input);
const names = (o: Partial<Record<BlockName, unknown>>) => Object.keys(o) as BlockName[];

describe("every block has exactly one owning surface", () => {
  test("no block is lost: the two surfaces together render all of them", () => {
    const all = new Set(Object.keys(SURFACE_OF));
    const rendered = new Set<string>();
    // Absent blocks are omitted from a surface's output, so use an input where
    // everything is present at once.
    const blocks = blocksFor({
      phase: "STUDY",
      multiAnchor: true,
      openGapCount: 2,
      attemptCount: 3,
      revealed: true,
      hasReveal: true,
    });
    for (const surface of SURFACES) {
      for (const name of names(surfaceBlocks(blocks, surface))) rendered.add(name);
    }
    expect(rendered).toEqual(all);
  });

  test("no block is owned by both surfaces", () => {
    for (const block of Object.keys(SURFACE_OF) as BlockName[]) {
      const owners = SURFACES.filter((s) => surfaceOf(block) === s);
      expect(owners, block).toHaveLength(1);
    }
  });

  test("the purpose split is the one the document states", () => {
    // Written out rather than derived, so a change of mind has to be a change of
    // mind here as well as in the code.
    expect(surfaceOf("setup")).toBe("lesson");
    expect(surfaceOf("tracePath")).toBe("lesson");
    expect(surfaceOf("reveal")).toBe("lesson");
    expect(surfaceOf("question")).toBe("understanding");
    expect(surfaceOf("feedback")).toBe("understanding");
    expect(surfaceOf("gaps")).toBe("understanding");
    expect(surfaceOf("attempts")).toBe("understanding");
  });
});

describe("the setup's mirror, which is the only duplication allowed", () => {
  test("exactly one block is mirrored, and it is the setup", () => {
    expect(Object.keys(MIRRORED)).toEqual(["setup"]);
    expect(MIRRORED.setup).toBe("understanding");
  });

  test("the mirror is never expanded, in any phase", () => {
    // An expanded mirror would put the longest thing on the page into both
    // surfaces at once — the accumulation L4 removed, reintroduced sideways.
    for (const input of every) {
      const inUnderstanding = surfaceBlocks(blocksFor(input), "understanding").setup;
      expect(inUnderstanding, JSON.stringify(input)).not.toBe("open");
    }
  });

  test("the mirror shows nothing when the block is absent everywhere", () => {
    // `setup` is never absent today, so this is asserted through the function's
    // contract rather than through a reachable phase.
    const blocks = { ...blocksFor(every[0]), setup: "absent" } as LessonBlocks;
    expect(surfaceBlocks(blocks, "understanding").setup).toBe("absent");
  });

  test("STUDY: expanded in Lesson, collapsed in Understanding, same moment", () => {
    const blocks = blocksFor({
      phase: "STUDY",
      multiAnchor: false,
      openGapCount: 0,
      attemptCount: 0,
      revealed: false,
      hasReveal: true,
    });
    expect(surfaceBlocks(blocks, "lesson").setup).toBe("open");
    expect(surfaceBlocks(blocks, "understanding").setup).toBe("collapsed");
  });
});

describe("the question the verdict superseded", () => {
  const base = { multiAnchor: true, openGapCount: 2, attemptCount: 3, hasReveal: true };

  test("collapsed once a verdict is up, in both reporting phases", () => {
    for (const phase of ["FEEDBACK", "RESOLVED"] as LessonPhase[]) {
      const blocks = blocksFor({ ...base, phase, revealed: true });
      expect(surfaceBlocks(blocks, "understanding").question, phase).toBe("collapsed");
    }
  });

  test("open while it IS the question, never both", () => {
    for (const phase of ["STUDY", "VERIFY"] as LessonPhase[]) {
      const blocks = blocksFor({ ...base, phase, revealed: true });
      expect(surfaceBlocks(blocks, "understanding").question, phase).toBe("open");
      expect(surfaceBlocks(blocks, "understanding").feedback, phase).toBe("absent");
    }
  });

  test("it never appears on Lesson, collapsed or otherwise", () => {
    // Being asked something is not reading. The echo is evidence-side context.
    for (const input of every) {
      expect(surfaceBlocks(blocksFor(input), "lesson").question, JSON.stringify(input))
        .toBeUndefined();
    }
  });

  test("collapsing it does not add an expanded block anywhere", () => {
    // The R3 and R2 caps below are counted over `open` only, so this must not have
    // moved either number. Asserted directly because a rule that quietly raised the
    // open count would defeat the milestone it belongs to.
    for (const input of every) {
      const blocks = blocksFor(input);
      expect(openCountIn(blocks, "understanding"), JSON.stringify(input))
        .toBeLessThanOrEqual(2);
    }
  });
});

describe("R2 · the current thing is never behind both a tab and a disclosure", () => {
  test("every phase's live artifacts are expanded in their own surface", () => {
    // Read through `surfaceBlocks`, not off `lessonBlocks`: the weight that matters
    // is the one the surface renders, and for the setup those differ by design.
    for (const input of every) {
      const blocks = blocksFor(input);
      for (const block of liveArtifacts(input.phase, blocks)) {
        const state = surfaceBlocks(blocks, surfaceOf(block))[block];
        expect(state, `${block} in ${JSON.stringify(input)}`).toBe("open");
      }
    }
  });

  test("Understanding always has exactly one live artifact, never two", () => {
    // `question` and `feedback` are mutually exclusive in `lessonBlocks`. If that
    // ever stopped being true, Understanding would show a composer and a verdict
    // for the same answer — which is the state L4 exists to prevent.
    for (const input of every) {
      const blocks = blocksFor(input);
      const live = liveArtifacts(input.phase, blocks).filter(
        (b) => surfaceOf(b) === "understanding"
      );
      expect(live, JSON.stringify(input)).toHaveLength(1);
    }
  });

  test("each surface has at least one expanded block in every phase", () => {
    // A surface with everything collapsed is a tab that looks broken. Lesson's
    // floor is the setup or the explanation; Understanding's is the live artifact.
    for (const input of every) {
      const blocks = blocksFor(input);
      for (const surface of SURFACES) {
        expect(openCountIn(blocks, surface), `${surface} in ${JSON.stringify(input)}`)
          .toBeGreaterThanOrEqual(1);
      }
    }
  });
});

describe("R3 · Lesson never becomes an accumulating document", () => {
  test("Lesson never has more than two expanded sections", () => {
    for (const input of every) {
      expect(openCountIn(blocksFor(input), "lesson"), JSON.stringify(input))
        .toBeLessThanOrEqual(2);
    }
  });

  test("and today it is exactly one, which is the headroom S5 spends", () => {
    // Stronger than R3 asks. The setup and the explanation supersede each other
    // within Lesson, so one of them is expanded and never both; the trace path is
    // collapsed always. S5's newest adaptive section becomes the second, still
    // inside the cap.
    for (const input of every) {
      expect(openCountIn(blocksFor(input), "lesson"), JSON.stringify(input)).toBe(1);
    }
  });

  test("Understanding is held to the same cap, though only R3 requires it of Lesson", () => {
    for (const input of every) {
      expect(openCountIn(blocksFor(input), "understanding"), JSON.stringify(input))
        .toBeLessThanOrEqual(2);
    }
  });

  test("the single canvas's worst case of 4 becomes 1 and 2", () => {
    // The revisit case §3a's count test found: setup, gaps, question and reveal all
    // open together in one column. This is the measurable claim of the milestone —
    // and the split is better than a halving, because the setup and the explanation
    // supersede each other once they are on the same surface.
    const worst: ViewInput = {
      phase: "STUDY",
      multiAnchor: true,
      openGapCount: 2,
      attemptCount: 3,
      revealed: true,
      hasReveal: true,
    };
    const blocks = blocksFor(worst);
    expect(openCount(blocks)).toBe(4);
    expect(openCountIn(blocks, "lesson")).toBe(1);
    expect(openCountIn(blocks, "understanding")).toBe(2);
  });
});

describe("phase by phase, surface by surface", () => {
  const base = { multiAnchor: true, openGapCount: 2, attemptCount: 3, hasReveal: true };

  test("STUDY, first visit: Lesson is the prose, Understanding is the question", () => {
    const blocks = blocksFor({ ...base, phase: "STUDY", revealed: false });
    expect(surfaceBlocks(blocks, "lesson")).toEqual({
      setup: "open",
      tracePath: "collapsed",
      reveal: "absent",
      // Nothing has been re-taught, so there is nothing to have replaced.
      earlier: "absent",
    });
    expect(surfaceBlocks(blocks, "understanding")).toEqual({
      setup: "collapsed",
      question: "open",
      // Open here and only here: in STUDY the gaps are what the learner is
      // answering about, not something a verdict has superseded.
      gaps: "open",
      attempts: "collapsed",
      feedback: "absent",
    });
  });

  test("FEEDBACK: Lesson holds the explanation, Understanding holds the verdict", () => {
    const blocks = blocksFor({ ...base, phase: "FEEDBACK", revealed: true });
    const lesson = surfaceBlocks(blocks, "lesson");
    const understanding = surfaceBlocks(blocks, "understanding");
    expect(lesson.reveal).toBe("open");
    // The prose steps back the moment the explanation exists.
    expect(lesson.setup).toBe("collapsed");
    expect(understanding.feedback).toBe("open");
    // Collapsed, not absent: the verdict superseded the question, and "shown about
    // WHAT?" has to stay answerable on the surface built to answer it (§4).
    expect(understanding.question).toBe("collapsed");
    // The key point already names the leading gap, so the list is a disclosure.
    expect(understanding.gaps).toBe("collapsed");
  });

  test("VERIFY: the composer returns to Understanding, the verdict is gone", () => {
    const blocks = blocksFor({ ...base, phase: "VERIFY", revealed: true });
    const understanding = surfaceBlocks(blocks, "understanding");
    expect(understanding.question).toBe("open");
    expect(understanding.feedback).toBe("absent");
    // And Lesson does not change just because a check is outstanding: being
    // re-asked is not being re-taught.
    expect(surfaceBlocks(blocks, "lesson").reveal).toBe("open");
  });

  test("RESOLVED: Understanding reports, and nothing in Lesson moved", () => {
    const before = surfaceBlocks(blocksFor({ ...base, phase: "VERIFY", revealed: true }), "lesson");
    const blocks = blocksFor({ ...base, phase: "RESOLVED", revealed: true });
    expect(surfaceBlocks(blocks, "understanding").feedback).toBe("open");
    expect(surfaceBlocks(blocks, "lesson")).toEqual(before);
  });

  test("a single-anchor unit has no trace path in either surface", () => {
    const blocks = blocksFor({ ...base, multiAnchor: false, phase: "STUDY", revealed: false });
    expect(surfaceBlocks(blocks, "lesson").tracePath).toBe("absent");
    expect(surfaceBlocks(blocks, "understanding").tracePath).toBeUndefined();
  });

  test("a stop with no gaps and no attempts still gives Understanding its question", () => {
    const blocks = blocksFor({
      phase: "STUDY",
      multiAnchor: false,
      openGapCount: 0,
      attemptCount: 0,
      revealed: false,
      hasReveal: true,
    });
    expect(surfaceBlocks(blocks, "understanding")).toEqual({
      setup: "collapsed",
      question: "open",
      gaps: "absent",
      attempts: "absent",
      feedback: "absent",
    });
  });
});
