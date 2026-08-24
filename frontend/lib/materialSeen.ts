import type { Attempt, NodeGap } from "@/lib/api";

/**
 * Has the learner looked at the material since their answer rewrote it?
 *
 * ── The one fact the frontend owns ───────────────────────────────────────────
 *
 * M2 moved every learning decision to the server, on the rule that the client
 * must not reconstruct what the backend already knows. This is the exception the
 * rule allows for: **"have I looked at this tab"** is not a fact about the
 * learner's understanding and the server has no way to observe it. So it lives
 * here, in `localStorage`, and it is never allowed to mean anything more than it
 * says — reading is guidance, never evidence.
 *
 * ── What was wrong ───────────────────────────────────────────────────────────
 *
 * Exactly one outcome rewrites Lesson: a `reteach`, reachable only from a
 * `wrong_model` lead gap or from overflow collapse. It replaces `cached_lesson`
 * wholesale — new setup, new prompt, new reveal — and it happens while the
 * learner is on the Understanding tab looking at their verdict. So the system can
 * generate remediation written specifically for this learner's misconception and
 * they may never see it.
 *
 * Two signals existed and both had the wrong lifetime, in opposite directions:
 *
 *   the tab dot        React state in the page. A reload dropped it — and a
 *                      change forgotten on refresh is a change the learner never
 *                      saw. (`railSeenAt` already used localStorage for exactly
 *                      this reason; the surface dot simply had not.)
 *   the `Rewritten`
 *   callout            derived from the last attempt's `retaught` flag, so it
 *                      NEVER cleared — it sat on the lesson until the next
 *                      answer, long after it had been read.
 *
 * One forgot too fast and one never forgot. Both now read the same fact: the
 * material was installed at time T, and the learner last looked at time S.
 *
 * Pure except for the two storage accessors, which are the only reason this is a
 * module rather than a hook.
 */

const KEY = (sessionId: string, nodeId: string) =>
  `codeonboard:lesson-seen:${sessionId}:${nodeId}`;

/**
 * When the material now on screen was installed by a re-teach, or null.
 *
 * The LATEST landed re-teach, because that is the version currently rendered.
 * Read from the attempt record rather than from a live grading result so it
 * survives a reload — the question "is this different from what I read before"
 * does not stop being worth answering because the page was refreshed.
 *
 * Verification attempts are excluded: a verification never re-teaches, so an
 * entry from one would date the material to something that did not change it.
 */
export function retaughtAt(attempts: Attempt[]): string | null {
  let at: string | null = null;
  for (const attempt of attempts) {
    if ((attempt.kind ?? "assessment") === "verification") continue;
    if (attempt.response?.retaught !== true) continue;
    at = attempt.response.at ?? attempt.at ?? at;
  }
  return at;
}

/**
 * The misconceptions the re-teach was written to correct, by claim.
 *
 * **This is what makes the notice answer "what changed" rather than only "something
 * changed".** A badge solves navigation and not comprehension: a learner who
 * returns to a rewritten lesson still has to work out which part is new, and a
 * re-teach REPLACES the whole lesson, so there is no diff to highlight — every
 * field is regenerated.
 *
 * What there is instead is the reason: the backend already records which gaps the
 * lesson was told to correct (`response.gaps_addressed`), and the claims are
 * already on the wire. No new model call, no new field — the two halves were
 * simply never joined up.
 */
export function rewriteAnswers(attempts: Attempt[], gaps: NodeGap[]): string[] {
  const byId = new Map(gaps.map((g) => [g.id, g.claim]));
  for (let i = attempts.length - 1; i >= 0; i--) {
    const attempt = attempts[i];
    if ((attempt.kind ?? "assessment") === "verification") continue;
    if (attempt.response?.retaught !== true) continue;
    return (attempt.response.gaps_addressed ?? [])
      .map((id) => byId.get(id))
      .filter((claim): claim is string => Boolean(claim));
  }
  return [];
}

export function lastSeenAt(sessionId: string, nodeId: string): string | null {
  try {
    return window.localStorage.getItem(KEY(sessionId, nodeId));
  } catch {
    // Private mode, or storage disabled. Unknown reads as "not seen", which errs
    // toward showing the notice — the safe direction for a signal whose whole
    // purpose is that the learner does not miss something.
    return null;
  }
}

export function markSeen(sessionId: string, nodeId: string, at: string): void {
  try {
    window.localStorage.setItem(KEY(sessionId, nodeId), at);
  } catch {
    /* storage unavailable; the notice simply stays up */
  }
}

/**
 * Is there rewritten material the learner has not looked at since?
 *
 * String comparison on ISO-8601 UTC timestamps, which sort lexicographically —
 * both sides are written by `datetime.isoformat` server-side and `toISOString`
 * here, so this is exact rather than approximately right.
 */
export function materialUnread(
  installedAt: string | null,
  seenAt: string | null
): boolean {
  if (!installedAt) return false;
  if (!seenAt) return true;
  return installedAt > seenAt;
}
