import { describe, expect, it } from "vitest";
import type { Disposition, UnderstandingClass } from "@/lib/api";
import { standingLabel, standingOf, standingStyle, type Standing } from "@/lib/standing";
import { node } from "@/test/factories";
import { standingOfNode } from "@/lib/standing";

/**
 * M0 — the rail must not render a stop the learner answered the same way as one
 * they have never opened.
 *
 * The defect this file pins down, observed in a manual run: an `off-topic`
 * answer is excluded from evidence on purpose, so the stop classifies
 * `insufficient`; "Move on anyway" then recorded nothing; and the pin was a
 * dashed grey circle — byte-identical to an untouched stop, with no caption. The
 * learner's answer AND their decision were both invisible.
 *
 * The guarantee asserted throughout: **no disposition can make a stop read as
 * demonstrated.** A decision is not evidence, on the wire and on the pin alike.
 */

const DISPOSITIONS: Disposition[] = [
  "active",
  "continued",
  "waived",
  "skipped",
  "asserted",
];
const CLASSES: UnderstandingClass[] = [
  "strength",
  "recovered",
  "unresolved",
  "insufficient",
];

describe("standingOf", () => {
  it("reads an untouched stop as untouched", () => {
    expect(standingOf({ understanding: "insufficient", disposition: "active" })).toBe(
      "untouched"
    );
  });

  it("separates a stop that was answered from one that was never opened", () => {
    // THE DEFECT. Both are `insufficient`; only `attempted` tells them apart.
    expect(
      standingOf({
        understanding: "insufficient",
        disposition: "active",
        attempted: true,
      })
    ).toBe("attempted");
  });

  it("reads an assessed shortfall with nothing decided as open", () => {
    expect(
      standingOf({ understanding: "unresolved", disposition: "active", attempted: true })
    ).toBe("open");
  });

  it.each<Disposition>(["continued", "waived", "skipped", "asserted"])(
    "reads %s as set aside",
    (disposition) => {
      expect(
        standingOf({ understanding: "unresolved", disposition, attempted: true })
      ).toBe("set_aside");
    }
  );

  it("reads a settled stop with no evidence as set aside, not untouched", () => {
    // The off-topic-then-move-on case, end to end. Before M0 this returned the
    // same thing as a stop nobody had opened.
    expect(
      standingOf({
        understanding: "insufficient",
        disposition: "continued",
        attempted: true,
      })
    ).toBe("set_aside");
  });

  it("reads a deliberate skip as set aside even with no attempt", () => {
    expect(
      standingOf({ understanding: "insufficient", disposition: "skipped" })
    ).toBe("set_aside");
  });

  it.each<UnderstandingClass>(["strength", "recovered"])(
    "reads %s as demonstrated whatever was decided",
    (understanding) => {
      // A learner can waive a gap and LATER verify it — `waive_remaining`
      // survives a new answer by design — so the disposition is still on the
      // node while the evidence has moved past it. Evidence wins.
      for (const disposition of DISPOSITIONS) {
        expect(standingOf({ understanding, disposition })).toBe("demonstrated");
      }
    }
  );

  it("treats a missing understanding as insufficient, like every other surface", () => {
    expect(standingOf({})).toBe("untouched");
    expect(standingOf({ attempted: true })).toBe("attempted");
  });

  it("treats a graph served without `attempted` as the pre-M0 rendering", () => {
    // Additive field: an older payload must degrade to what it used to draw,
    // never to a claim it cannot support.
    expect(standingOf({ understanding: "insufficient", disposition: "active" })).toBe(
      "untouched"
    );
  });

  it("never lets a decision produce demonstrated understanding", () => {
    // THE INVARIANT, swept. This is the projection-layer twin of the server-side
    // test of the same name.
    for (const understanding of CLASSES) {
      for (const disposition of DISPOSITIONS) {
        for (const attempted of [true, false]) {
          const standing = standingOf({ understanding, disposition, attempted });
          if (standing === "demonstrated") {
            expect(["strength", "recovered"]).toContain(understanding);
          }
        }
      }
    }
  });
});

describe("standingOfNode", () => {
  it("reads the three facts straight off a node", () => {
    expect(
      standingOfNode(
        node("a", {
          understanding: "insufficient",
          disposition: "continued",
          attempted: true,
        })
      )
    ).toBe("set_aside");
  });
});

describe("standingStyle", () => {
  it("marks only the settled standing with the bar", () => {
    const settled: Record<Standing, boolean> = {
      demonstrated: false,
      open: false,
      attempted: false,
      untouched: false,
      set_aside: true,
    };
    for (const [standing, expected] of Object.entries(settled)) {
      expect(standingStyle(standing as Standing, "unresolved").settled).toBe(expected);
    }
  });

  it("keeps the dash for untouched and drops it once something has happened", () => {
    // The dash carries exactly one bit — "nothing has happened here" — so it is
    // the one channel that must not also mean something else.
    expect(standingStyle("untouched", "insufficient").borderStyle).toBe("dashed");
    expect(standingStyle("attempted", "insufficient").borderStyle).toBe("solid");
    expect(standingStyle("set_aside", "insufficient").borderStyle).toBe("solid");
  });

  it("keeps the evidence colour through a decision", () => {
    // What the learner decided must not overwrite what the evidence says: a stop
    // set aside at `unresolved` and one set aside with no evidence at all are
    // different facts, and one colour for both would erase the difference.
    const stuck = standingStyle("set_aside", "unresolved");
    const blank = standingStyle("set_aside", "insufficient");
    expect(stuck.stroke).not.toBe(blank.stroke);
    expect(stuck.settled && blank.settled).toBe(true);
  });
});

describe("standingLabel", () => {
  it("names the two standings the evidence class cannot say on its own", () => {
    expect(standingLabel("attempted")).toBeTruthy();
    expect(standingLabel("set_aside")).toBeTruthy();
  });

  it("stays silent where the class already speaks for itself", () => {
    expect(standingLabel("demonstrated")).toBeNull();
    expect(standingLabel("open")).toBeNull();
    expect(standingLabel("untouched")).toBeNull();
  });
});
