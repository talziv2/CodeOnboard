import { beforeEach, describe, expect, test } from "vitest";
import type { Attempt, NodeGap } from "@/lib/api";
import {
  lastSeenAt,
  markSeen,
  materialUnread,
  retaughtAt,
  rewriteAnswers,
} from "@/lib/materialSeen";

/**
 * M3 — the learner must be able to find, and recognise, material their own
 * answer caused to be written.
 *
 * Exactly one outcome rewrites Lesson: a `reteach`. It replaces `cached_lesson`
 * wholesale, and it happens while the learner is on Understanding looking at
 * their verdict — so the system can generate remediation aimed at this learner's
 * misconception and they may never see it.
 *
 * Two signals existed and both had the wrong lifetime, in opposite directions:
 * the tab dot was React state and died on reload, while the `Rewritten` callout
 * was derived from the last attempt and never cleared at all. One forgot too
 * fast, one never forgot. Both now read the same pair of facts — installed at T,
 * last looked at S.
 */

const at = (iso: string): Attempt => ({
  answer: "an answer",
  classification: "confused",
  rationale: "r",
  at: iso,
});

const retaught = (iso: string, over: Partial<Attempt["response"]> = {}): Attempt => ({
  ...at(iso),
  response: { action: "reteach", retaught: true, at: iso, ...over },
});

describe("retaughtAt", () => {
  test("is null when nothing has rewritten the material", () => {
    expect(retaughtAt([])).toBeNull();
    expect(retaughtAt([at("2026-01-01T00:00:00Z")])).toBeNull();
  });

  test("is the LATEST landed re-teach, because that is what is on screen", () => {
    expect(
      retaughtAt([
        retaught("2026-01-01T00:00:00Z"),
        at("2026-01-02T00:00:00Z"),
        retaught("2026-01-03T00:00:00Z"),
      ])
    ).toBe("2026-01-03T00:00:00Z");
  });

  test("ignores a re-teach that failed", () => {
    // `retaught: false` means the call raised and `cached_lesson` was never
    // assigned. Dating the material to it would claim a rewrite that never
    // happened, and put a notice on a lesson nobody changed.
    const attempts = [
      { ...at("2026-01-01T00:00:00Z"), response: { action: "reteach", retaught: false } },
    ];
    expect(retaughtAt(attempts)).toBeNull();
  });

  test("ignores verification attempts", () => {
    // A verification never re-teaches, so an entry from one would date the
    // material to something that did not change it.
    const attempts = [{ ...retaught("2026-01-05T00:00:00Z"), kind: "verification" }];
    expect(retaughtAt(attempts)).toBeNull();
  });
});

describe("materialUnread", () => {
  test("nothing was rewritten, so nothing is unread", () => {
    expect(materialUnread(null, null)).toBe(false);
    expect(materialUnread(null, "2026-01-01T00:00:00Z")).toBe(false);
  });

  test("rewritten and never looked at", () => {
    expect(materialUnread("2026-01-02T00:00:00Z", null)).toBe(true);
  });

  test("looked at BEFORE the rewrite is still unread", () => {
    // The case the old dot could not express: the learner had read this stop, and
    // then their answer changed it underneath them.
    expect(materialUnread("2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z")).toBe(true);
  });

  test("looked at since the rewrite clears it", () => {
    // And this is the half the old CALLOUT could not express: it stayed up until
    // the next answer, long after it had been read.
    expect(materialUnread("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")).toBe(false);
  });
});

describe("rewriteAnswers", () => {
  const gaps: NodeGap[] = [
    { id: "g1", kind: "wrong_model", claim: "Adapters own cookie state.", blocking: true, status: "open" },
    { id: "g2", kind: "wrong_model", claim: "urllib3 applies the auth header.", blocking: true, status: "open" },
  ];

  test("names the misconceptions the rewrite was written to correct", () => {
    // A badge solves navigation and not comprehension. There is no diff to
    // highlight — every field is regenerated — so what changed is best answered
    // by what it was written to fix.
    const attempts = [retaught("2026-01-01T00:00:00Z", { gaps_addressed: ["g1", "g2"] })];
    expect(rewriteAnswers(attempts, gaps)).toEqual([
      "Adapters own cookie state.",
      "urllib3 applies the auth header.",
    ]);
  });

  test("reads the LATEST rewrite, not an older one", () => {
    const attempts = [
      retaught("2026-01-01T00:00:00Z", { gaps_addressed: ["g1"] }),
      retaught("2026-01-03T00:00:00Z", { gaps_addressed: ["g2"] }),
    ];
    expect(rewriteAnswers(attempts, gaps)).toEqual(["urllib3 applies the auth header."]);
  });

  test("drops an id with no claim on the wire rather than rendering a blank", () => {
    const attempts = [retaught("2026-01-01T00:00:00Z", { gaps_addressed: ["g1", "gone"] })];
    expect(rewriteAnswers(attempts, gaps)).toEqual(["Adapters own cookie state."]);
  });

  test("is empty when the re-teach recorded no targets", () => {
    // Every flag-off session, and every re-teach chosen from the scalar rather
    // than from gap objects. The notice degrades to "something changed", which is
    // what it said before — never to an invented reason.
    expect(rewriteAnswers([retaught("2026-01-01T00:00:00Z")], gaps)).toEqual([]);
  });
});

describe("the seen mark", () => {
  beforeEach(() => window.localStorage.clear());

  test("round-trips per session and node", () => {
    markSeen("s1", "n1", "2026-01-02T00:00:00Z");
    expect(lastSeenAt("s1", "n1")).toBe("2026-01-02T00:00:00Z");
    // Per NODE: reading one stop says nothing about another.
    expect(lastSeenAt("s1", "n2")).toBeNull();
    expect(lastSeenAt("s2", "n1")).toBeNull();
  });

  test("unknown reads as not-seen", () => {
    // The safe direction for a signal whose whole purpose is that the learner
    // does not miss something: err toward showing it.
    expect(lastSeenAt("s1", "n1")).toBeNull();
    expect(materialUnread("2026-01-01T00:00:00Z", lastSeenAt("s1", "n1"))).toBe(true);
  });
});
