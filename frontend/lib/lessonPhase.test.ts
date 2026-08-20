import { describe, expect, test } from "vitest";
import { isAsking, isCheckResult, lessonPhase, type LessonPhase } from "@/lib/lessonPhase";

/**
 * The branch table.
 *
 * The claim L1 makes is that thirteen enumerated situations are four states, and
 * the value of the claim is entirely in it being checked. So every situation the
 * plan lists gets a row here, named as the plan names it, and the assertion is
 * which phase it is — including, importantly, the many rows that are the SAME
 * phase. Those rows are not redundant: "confused with a warm-up inserted" and
 * "partial with no gaps" being one state is the finding.
 *
 * The companion assertions — that each phase matches what the panel actually
 * renders — live in `components/LessonPanel.test.tsx`, because they need a render.
 */

const ASSESSMENT = (over: Record<string, unknown> = {}) => ({
  classification: "understood",
  ...over,
});
const CHECK = (over: Record<string, unknown> = {}) => ({
  kind: "verification",
  classification: null,
  ...over,
});
const QUESTION = { node_id: "n1", question: "What can still fail?", targets: ["g1"], gaps: [] };

/** Each row: [situation, state, expected phase]. */
const TABLE: [string, Parameters<typeof lessonPhase>[0], LessonPhase][] = [
  // ── nothing graded on screen ───────────────────────────────────────────────
  ["fresh arrival", { result: null, verification: null }, "STUDY"],
  // A revisit has attempts, but attempts are not an input: they change what the
  // phase contains, never which phase it is. The learner is reading again.
  ["revisit (attempts exist, nothing graded this visit)", { result: null, verification: null }, "STUDY"],
  ["after 'Not now' on a verification offer", { result: null, verification: null }, "STUDY"],
  ["after clearing a verdict to answer again", { result: null, verification: null }, "STUDY"],

  // ── an assessment verdict is on screen ────────────────────────────────────
  ["understood", { result: ASSESSMENT(), verification: null }, "FEEDBACK"],
  [
    "partial with open gaps",
    { result: ASSESSMENT({ classification: "partial", gaps: [{ id: "g1" }] }), verification: null },
    "FEEDBACK",
  ],
  [
    "partial with no gaps",
    { result: ASSESSMENT({ classification: "partial", gaps: [] }), verification: null },
    "FEEDBACK",
  ],
  [
    "confused, warm-up inserted",
    {
      result: ASSESSMENT({ classification: "confused", mutation: { kind: "prerequisite" } }),
      verification: null,
    },
    "FEEDBACK",
  ],
  [
    "confused, warm-up declined by the Mutator",
    {
      result: ASSESSMENT({ classification: "confused", mutation: { kind: "none" } }),
      verification: null,
    },
    "FEEDBACK",
  ],
  [
    "re-taught",
    { result: ASSESSMENT({ adaptation: { retaught: true } }), verification: null },
    "FEEDBACK",
  ],
  [
    "pruned",
    { result: ASSESSMENT({ adaptation: { pruned: 2 } }), verification: null },
    "FEEDBACK",
  ],
  [
    "the pending-attempt path (warm-up inserted, graph refresh skipped)",
    {
      result: ASSESSMENT({ classification: "partial", mutation: { kind: "prerequisite" } }),
      verification: null,
    },
    "FEEDBACK",
  ],
  [
    "waived (a gap set aside)",
    { result: ASSESSMENT({ classification: "partial", gaps: [] }), verification: null },
    "FEEDBACK",
  ],
  ["off-topic", { result: ASSESSMENT({ classification: "off-topic" }), verification: null }, "FEEDBACK"],

  // ── a question is outstanding ─────────────────────────────────────────────
  ["verification outstanding", { result: null, verification: QUESTION }, "VERIFY"],

  // ── a check has reported ──────────────────────────────────────────────────
  ["verification answered, gaps cleared", { result: CHECK({ resolved: ["g1"], unresolved: [] }), verification: null }, "RESOLVED"],
  ["verification answered, partly cleared", { result: CHECK({ resolved: ["g1"], unresolved: ["g2"] }), verification: null }, "RESOLVED"],
  ["verification answered, nothing cleared", { result: CHECK({ resolved: [], unresolved: ["g1"] }), verification: null }, "RESOLVED"],
];

describe("the phase of every situation in the plan", () => {
  for (const [situation, state, expected] of TABLE) {
    test(`${situation} -> ${expected}`, () => {
      expect(lessonPhase(state)).toBe(expected);
    });
  }

  test("thirteen-plus situations collapse to exactly four phases", () => {
    const seen = new Set(TABLE.map(([, state]) => lessonPhase(state)));
    expect([...seen].sort()).toEqual(["FEEDBACK", "RESOLVED", "STUDY", "VERIFY"]);
    // And the crowded one really is one state, not a family of them.
    const feedbackRows = TABLE.filter(([, s]) => lessonPhase(s) === "FEEDBACK");
    expect(feedbackRows.length).toBeGreaterThanOrEqual(10);
  });
});

describe("the distinction a check must keep", () => {
  test("a check is not an assessment, even though both arrive as `result`", () => {
    // The backend returns `classification: null` on a check on purpose, so every
    // branch keyed off classification is silent here. Treating this as FEEDBACK
    // is the D2b bug: a working backend and a UI that said nothing.
    expect(isCheckResult(CHECK())).toBe(true);
    expect(isCheckResult(ASSESSMENT())).toBe(false);
    expect(isCheckResult(null)).toBe(false);
    expect(lessonPhase({ result: CHECK(), verification: null })).toBe("RESOLVED");
    expect(lessonPhase({ result: ASSESSMENT(), verification: null })).toBe("FEEDBACK");
  });

  test("an explicit assessment kind is still an assessment", () => {
    expect(lessonPhase({ result: { kind: "assessment" }, verification: null })).toBe("FEEDBACK");
  });
});

describe("an outstanding question always wins", () => {
  test("a verification outranks a verdict that somehow survived beside it", () => {
    // The two are mutually exclusive today — requesting clears `result`, answering
    // clears `verification`. The ordering is asserted anyway: a future path that
    // set both must render the unanswered question, not a verdict over the top of
    // it, which would put two composers on screen again.
    expect(lessonPhase({ result: ASSESSMENT(), verification: QUESTION })).toBe("VERIFY");
    expect(lessonPhase({ result: CHECK(), verification: QUESTION })).toBe("VERIFY");
  });

  test("undefined is treated as absent, not as an outstanding question", () => {
    expect(lessonPhase({ result: null, verification: undefined })).toBe("STUDY");
  });
});

describe("which phases are asking a question", () => {
  test("the two that own a question, not the two that own a report", () => {
    expect(isAsking("STUDY")).toBe(true);
    expect(isAsking("VERIFY")).toBe(true);
    expect(isAsking("FEEDBACK")).toBe(false);
    expect(isAsking("RESOLVED")).toBe(false);
  });
});
