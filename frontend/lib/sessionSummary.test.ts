import { describe, expect, it } from "vitest";
import { relativeTime, repoLabel, sessionTitle } from "@/lib/sessionSummary";
import type { SessionSummary } from "@/lib/api";

const base: SessionSummary = {
  session_id: "s1", repo_url: "https://github.com/psf/requests", repo_id: "r1",
  goal: {}, title: null, status: "active", current_node_id: null,
  created_at: null, updated_at: null, last_active_at: null, archived_at: null,
  progress: { goal_readiness: null, stops_settled: null, stops_total: null },
};

describe("repoLabel", () => {
  it("says which repository the way a person would", () => {
    expect(repoLabel("https://github.com/psf/requests")).toBe("psf/requests");
  });

  it("collapses the spellings that exist in the real database", () => {
    // The live data holds five spellings of three repositories.
    expect(repoLabel("https://github.com/psf/requests/")).toBe("psf/requests");
    expect(repoLabel("https://github.com/psf/requests.git")).toBe("psf/requests");
  });
});

describe("sessionTitle", () => {
  it("prefers the stored title — the learner may have renamed it", () => {
    expect(sessionTitle({ ...base, title: "Connection pooling", goal: { focus_area: "auth" } }))
      .toBe("Connection pooling");
  });

  it("falls back to the goal's own words", () => {
    expect(sessionTitle({ ...base, goal: { focus_area: "request signing" } }))
      .toBe("Request signing");
  });

  it("never renders an empty heading", () => {
    // A card with no name is a card you cannot pick out of a list.
    expect(sessionTitle(base)).toBe("psf/requests");
    expect(sessionTitle({ ...base, title: "   " })).toBe("psf/requests");
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-08-22T12:00:00Z");

  it("answers 'when was I last here' in the reader's terms", () => {
    expect(relativeTime("2026-08-22T11:00:00Z", now)).toBe("1 hour ago");
    expect(relativeTime("2026-08-22T09:00:00Z", now)).toBe("3 hours ago");
    expect(relativeTime("2026-08-20T12:00:00Z", now)).toBe("2 days ago");
  });

  it("switches to a date past a week", () => {
    // "23 days ago" is arithmetic the reader has to do; "Jul 30" is a fact.
    expect(relativeTime("2026-07-30T12:00:00Z", now)).toMatch(/Jul/);
  });

  it("returns null rather than guessing when there is no timestamp", () => {
    // So the caller omits the line instead of claiming "just now" about a
    // session whose age is unknown.
    expect(relativeTime(null, now)).toBeNull();
    expect(relativeTime("not a date", now)).toBeNull();
  });

  it("reads the SQLite timestamp format the store actually writes", () => {
    expect(relativeTime("2026-08-22 11:00:00.000", now)).toBe("1 hour ago");
  });

  it("does not shift a timestamp that already states its zone", () => {
    expect(relativeTime("2026-08-22T11:00:00+00:00", now)).toBe("1 hour ago");
    expect(relativeTime("2026-08-22T13:00:00+02:00", now)).toBe("1 hour ago");
  });

  it("never reports a past timestamp as being in the future", () => {
    // What the timezone bug looked like from the reader's side: west of UTC,
    // a marker-less UTC string parsed as local lands ahead of `now`.
    for (const stamp of ["2026-08-22 11:59:00.000", "2026-08-22T11:59:00Z"]) {
      expect(relativeTime(stamp, now)).not.toBeNull();
      expect(relativeTime(stamp, now)).toBe("just now");
    }
  });
});
