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


/**
 * Is the Tutor's UI built into this bundle?
 *
 * Mirrors the backend's `CODEONBOARD_TUTOR`, and the two are deliberately
 * separate variables rather than one: they are read in different processes at
 * different times. The backend's gates BEHAVIOUR at request time (the routes
 * answer 404); this one gates whether the CHAT control is drawn at all, at build
 * time, because Next inlines `NEXT_PUBLIC_*`.
 *
 * ── DEFAULT ON, and why the comparison points this way ────────────────────────
 *
 * Unset means ENABLED, so this reads `!== "0"` rather than `=== "1"`. The two are
 * not stylistic variants of each other; the direction of the comparison IS the
 * default, and it is the reason a fresh clone with no `.env.local` now builds a
 * bundle that has the Tutor in it.
 *
 * THE FAILURE THIS PREVENTS. `=== "1"` meant an absent variable compiled the CHAT
 * control out, silently and with no error anywhere. A fresh clone ran the complete
 * backend behind a UI that had no way to reach it, and the only symptom was a
 * feature that appeared not to have been built. Next inlining `NEXT_PUBLIC_*`
 * makes that worse, not better: the variable has to exist at BUILD time, so even
 * setting it in a running shell and reloading changes nothing, which is exactly
 * the kind of non-symptom that costs an afternoon.
 *
 * An unrecognised value enables, matching `lessonUi`'s rule that a fallback lands
 * on the default rather than throwing — now that the default is on, a typo can no
 * longer take the feature away.
 *
 * THE PAIRING TO KEEP IN MIND. The safe direction is backend-off / bundle-on: the
 * control appears and the panel reports a failure, which is noisy but harmless.
 * With this off, no Tutor code is reachable whatever the backend does. Both now
 * default on, so the fresh-clone case is the fully-working one.
 *
 * Neither gates STORAGE. A conversation written with both on survives both being
 * turned off (see `backend/learning/flags.py`).
 */
export function tutorUi(): boolean {
  return process.env.NEXT_PUBLIC_CODEONBOARD_TUTOR !== "0";
}
