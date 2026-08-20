/**
 * The colour a verdict is spoken in, keyed by the classification the Grader
 * returns.
 *
 * Shared because two places say a verdict: the attempt history, where every past
 * answer carries its own, and the feedback state, where the current one does.
 * Moved here verbatim when `AttemptHistory` was extracted — one table, so the
 * history and the live verdict can never disagree about what `partial` looks
 * like.
 *
 * `RECOVERED` is not in here on purpose. Recovery is not a classification; it is
 * a relationship between attempts (a failure, then a warm-up, then an
 * `understood`), and it must never render in the failure colour.
 */
export const VERDICT_COLOR: Record<string, string> = {
  understood: "var(--color-jade)",
  partial: "var(--color-brass)",
  confused: "var(--color-rust)",
  "off-topic": "var(--color-rust)",
};

/** For a classification this table does not know — a new one must read as neutral, not as failure. */
export const NEUTRAL = "var(--color-chalk)";
