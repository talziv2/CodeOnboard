/**
 * Build-time UI flags.
 *
 * One flag, following the pattern the backend already uses for risky changes
 * (`CODEONBOARD_CURRICULUM`, `CODEONBOARD_GAPS`): the new behaviour is opt-in
 * while it is being proven, and the old path stays reachable without a revert.
 *
 * `NEXT_PUBLIC_CODEONBOARD_UI`:
 *   "legacy" (default) — the lesson renderer as it shipped
 *   "next"             — the phase-driven workspace
 *
 * Read through `lessonUi()` rather than the env var directly, so the default is
 * decided in exactly one place. Next inlines `NEXT_PUBLIC_*` at build time, so
 * this is a build flag, not a runtime toggle — which is what we want: a session
 * must not change renderer underneath a learner mid-answer.
 */

export type LessonUi = "legacy" | "next";

export function lessonUi(): LessonUi {
  return process.env.NEXT_PUBLIC_CODEONBOARD_UI === "next" ? "next" : "legacy";
}
