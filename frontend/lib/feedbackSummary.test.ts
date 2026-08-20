import { describe, expect, test } from "vitest";
import type { NodeGap, RespondResult } from "@/lib/api";
import { consequenceLine, keyPoint } from "@/lib/feedbackSummary";
import { t } from "@/lib/strings";

/**
 * The key point ladder and the single consequence line.
 *
 * The ladder's value is that it degrades to something TRUE rather than to nothing,
 * so each level is asserted with the levels above it removed — which is the only way
 * to know the fallback is reachable rather than theoretical.
 */

const blocking: NodeGap = { id: "g1", kind: "wrong_model", claim: "a connected graph cannot fail", blocking: true };
const soft: NodeGap = { id: "g2", kind: "right_idea_wrong_altitude", claim: "h() is always admissible", blocking: false };

describe("the key point ladder", () => {
  test("level 1: the Grader's own headline wins when it exists", () => {
    const line = keyPoint(
      { classification: "partial", headline: "Not quite — Graph is directed by default." },
      [blocking],
      "Partly there"
    );
    expect(line).toBe("Not quite — Graph is directed by default.");
  });

  test("level 2: composed from the leading gap when there is no headline", () => {
    const line = keyPoint({ classification: "partial" }, [blocking], "Partly there");
    expect(line).toBe(t.lesson.keyPoint("Partly there", blocking.claim));
    // Framed as an assumption carried, not as a correction nobody computed.
    expect(line).toContain("working from");
  });

  test("level 2 prefers a BLOCKING gap over a softer one, whatever the order", () => {
    const line = keyPoint({ classification: "partial" }, [soft, blocking], "Partly there");
    expect(line).toContain(blocking.claim);
    expect(line).not.toContain(soft.claim);
  });

  test("level 2 falls to the first gap when none is blocking", () => {
    const line = keyPoint({ classification: "partial" }, [soft], "Partly there");
    expect(line).toContain(soft.claim);
  });

  test("level 3: the verdict word alone, for a session with no gaps on the wire", () => {
    expect(keyPoint({ classification: "confused" }, [], "Not quite")).toBe("Not quite");
  });

  // ── S0 defect 1 ─────────────────────────────────────────────────────────────
  test("the frame is never applied to an answer that reached the objective", () => {
    // Observed live, twice: "Understood — you're working from: requests only
    // supports two built-in auth classes and does not provide an extension point"
    // — on the answer that had just refuted exactly that, correctly, and been
    // graded `understood` for it. Gaps close only by verification, so a gap opened
    // by an EARLIER attempt is still open here; the frame asserts a belief the
    // learner demonstrably does not hold.
    const line = keyPoint({ classification: "understood" }, [blocking], "Understood");
    expect(line).not.toContain("working from");
    expect(line).not.toContain(blocking.claim);
    expect(line).toBe(t.lesson.keyPointUnverified("Understood", 1));
  });

  test("what it says instead is the thing that is true, and it counts", () => {
    expect(keyPoint({ classification: "understood" }, [blocking, soft], "Understood")).toBe(
      t.lesson.keyPointUnverified("Understood", 2)
    );
  });

  test("understood with nothing open is still the bare verdict word", () => {
    expect(keyPoint({ classification: "understood" }, [], "Understood")).toBe("Understood");
  });

  test("the Grader's own headline still outranks the veto", () => {
    // Level 1 is the Grader's sentence about THIS answer, so it is right even when
    // a gap is outstanding — the veto only replaces what we compose ourselves.
    const line = keyPoint(
      { classification: "understood", headline: "That's it — the callable IS the contract." },
      [blocking],
      "Understood"
    );
    expect(line).toBe("That's it — the callable IS the contract.");
  });

  test("an empty or whitespace headline does not win", () => {
    expect(keyPoint({ classification: "partial", headline: "   " }, [blocking], "Partly")).toContain(
      blocking.claim
    );
    expect(keyPoint({ classification: "partial", headline: null }, [], "Partly")).toBe("Partly");
  });
});

describe("the single consequence line", () => {
  const r = (over: Partial<RespondResult>) => ({ classification: "confused", ...over }) as RespondResult;

  test("a warm-up that was added is the loudest thing that happened", () => {
    expect(
      consequenceLine(r({ mutation: { kind: "prerequisite" }, adaptation: { kind: "prerequisite" } }))
    ).toBe(t.lesson.consequenceWarmUpAdded);
  });

  test("a warm-up that already existed says so, not that one was added", () => {
    expect(
      consequenceLine(
        r({ mutation: { kind: "none", reason: "prerequisite_exists" }, adaptation: { kind: "prerequisite" } })
      )
    ).toBe(t.lesson.consequenceWarmUpExists);
  });

  test("a warm-up that could not be built is reported, not silent", () => {
    // Declining is a real answer; §3 requires it be said.
    expect(consequenceLine(r({ mutation: { kind: "none" }, adaptation: { kind: "prerequisite" } }))).toBe(
      t.lesson.consequenceWarmUpUnavailable
    );
  });

  test("pruning is reported with its count", () => {
    expect(consequenceLine(r({ adaptation: { kind: "hint", pruned: 3 } }))).toBe(
      t.lesson.consequencePruned(3)
    );
  });

  test("a re-teach is reported", () => {
    expect(consequenceLine(r({ adaptation: { kind: "hint", retaught: true } }))).toBe(
      t.lesson.consequenceRetaught
    );
  });

  test("only ONE line, even when several things happened at once", () => {
    // This is the whole point: these used to stack.
    const line = consequenceLine(
      r({
        mutation: { kind: "prerequisite" },
        adaptation: { kind: "prerequisite", retaught: true, pruned: 2 },
      })
    );
    expect(line).toBe(t.lesson.consequenceWarmUpAdded);
    expect(line).not.toContain("no longer needed");
    expect(line).not.toContain("rewritten");
  });

  test("nothing happened, nothing said", () => {
    expect(consequenceLine(r({ adaptation: { kind: "hint", text: "A hint." } }))).toBeNull();
    expect(consequenceLine(r({}))).toBeNull();
  });

  test("pruning of zero is not an event", () => {
    expect(consequenceLine(r({ adaptation: { kind: "hint", pruned: 0 } }))).toBeNull();
  });
});
