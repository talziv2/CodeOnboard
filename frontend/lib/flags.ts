/**
 * Build-time UI flags.
 *
 * One flag, following the pattern the backend already uses for risky changes
 * (`CODEONBOARD_CURRICULUM`, `CODEONBOARD_GAPS`): the new behaviour is opt-in
 * while it is being proven, and the old path stays reachable without a revert.
 *
 * `NEXT_PUBLIC_CODEONBOARD_UI`:
 *   "legacy" (default) — the lesson renderer as it shipped
 *   "next"             — the phase-driven single canvas (L4)
 *   "surfaces"         — Lesson / Understanding / Map
 *
 * THREE VALUES, NOT TWO, and deliberately so: this decision has already been
 * revised once. `ui-direction.md` §13 rejected tabs on the evidence available then
 * and named the triggers that would justify revisiting; L3 and L4 ran the
 * single-canvas experiment it asked for, it worked measurably, and manual
 * inspection still found the session heavy. `next` therefore has to stay
 * reachable — not as a fallback, but as the thing `surfaces` is measured against
 * (S6 compares both against S0's live baseline). Collapsing it to a boolean would
 * throw away the only comparison that can say whether the revision was right.
 *
 * Unknown values fall back to `legacy` rather than throwing: a typo in an env var
 * should not take the app down, and the shipped renderer is the safe answer.
 *
 * Read through `lessonUi()` rather than the env var directly, so the default is
 * decided in exactly one place. Next inlines `NEXT_PUBLIC_*` at build time, so
 * this is a build flag, not a runtime toggle — which is what we want: a session
 * must not change renderer underneath a learner mid-answer.
 */

export type LessonUi = "legacy" | "next" | "surfaces";

export function lessonUi(): LessonUi {
  const value = process.env.NEXT_PUBLIC_CODEONBOARD_UI;
  return value === "next" || value === "surfaces" ? value : "legacy";
}

/**
 * Does this path render from the phase-driven view model?
 *
 * `surfaces` is a re-placement of L4's blocks, not a replacement for them — it
 * reuses `lessonPhase`, `lessonBlocks`, `feedbackActions` and the block components
 * whole (§6). So every `ui === "next"` test in the panel means "the phase-driven
 * model, either arrangement of it", and writing that as a predicate is what stops
 * S2 and S3 having to touch each of those call sites twice.
 */
export function isPhaseDriven(ui: LessonUi): boolean {
  return ui === "next" || ui === "surfaces";
}
