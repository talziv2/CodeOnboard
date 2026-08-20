/**
 * Build-time UI flags.
 *
 * `NEXT_PUBLIC_CODEONBOARD_UI`:
 *   "surfaces" (default) — Lesson · Understanding · Map
 *   "next"               — the single phase-driven canvas, L4's arrangement
 *
 * ── What happened to `legacy`, and why the other two remain ────────────────────
 *
 * There were three. `legacy` was the renderer as it shipped before the redesign,
 * kept reachable so the new information architecture could be proven before it was
 * the only path. It has now been proven twice: L4 measured against it (1565px to
 * 1127px, two primaries to one), and S6 measured against L4 (1747px in one column
 * to 1031 and 806 across two surfaces). Keeping a third arrangement alive meant
 * every behaviour change had to be made twice or consciously not made twice — which
 * is how `warmUpDeclined` came to be derived two different ways and stayed wrong on
 * one of them. L5 deletes it.
 *
 * `next` stays, and deliberately. It is the baseline S6's numbers are quoted
 * against, and the arrangement a human has not yet chosen between: the measurements
 * say the split is lighter, and whether it *reads* better is a judgement only use
 * settles. Deleting the alternative before that judgement would make the judgement
 * unaskable.
 *
 * THE DEFAULT IS NOW `surfaces`, which is the real change here. Before this, an
 * unset variable meant the pre-redesign renderer, so the whole redesign was opt-in;
 * now the flag exists to opt *out* of it. An unrecognised value still falls back to
 * the default rather than throwing — a typo should not take the app down — and the
 * default being the thing we believe is best is what makes that fallback safe.
 *
 * Read through `lessonUi()` rather than the env var directly, so the default is
 * decided in exactly one place. Next inlines `NEXT_PUBLIC_*` at build time, so this
 * is a build flag, not a runtime toggle — which is what we want: a session must not
 * change renderer underneath a learner mid-answer.
 */

export type LessonUi = "next" | "surfaces";

export function lessonUi(): LessonUi {
  return process.env.NEXT_PUBLIC_CODEONBOARD_UI === "next" ? "next" : "surfaces";
}

/**
 * Does this path draw one surface at a time?
 *
 * The only question the panel still has to ask about the flag. `surfaces` renders
 * the surface the tab selects; `next` renders every block in one column. Same view
 * model, same phase, same components — the difference is placement, which is why
 * this is a predicate rather than two code paths.
 *
 * Replaces `isPhaseDriven`, which asked whether the phase-driven model was in use
 * at all. Both remaining paths use it, so the question no longer has a false case.
 */
export function isSplitSurfaces(ui: LessonUi): boolean {
  return ui === "surfaces";
}
