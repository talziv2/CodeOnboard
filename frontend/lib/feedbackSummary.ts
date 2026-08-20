import type { NodeGap, RespondResult } from "@/lib/api";
import { t } from "@/lib/strings";

/**
 * The one line a learner reads first, and the one line about what the system did.
 *
 * §2 calls the first the **key point**, and it is the single condensation in the
 * flow. `ui-concept.md` §10.4 floated a second one above the explanation; that
 * stays dropped, because two places to feel finished is exactly the shallow-skipping
 * risk this design exists to avoid. The key point orients — it never substitutes,
 * which is why the Grader's full rationale sits immediately beneath it and is never
 * collapsed while a verdict is up.
 *
 * THE LADDER, best available first:
 *
 *   1. `headline` — a short corrective sentence, if the Grader supplies one. That
 *      needs the optional backend milestone B1, so it is read defensively and simply
 *      absent until then. Reading it now means L4 does not block on B1 and B1 needs
 *      no frontend change when it lands.
 *   2. Composed from the leading gap — the verdict word plus the blocking gap's
 *      claim, framed as an assumption the learner is CARRYING. Real data, no backend
 *      change, and the level that actually ships here.
 *   3. The verdict word alone — for pre-gap-model sessions with nothing on the wire.
 *
 * The same shape as `objective()` falling back to `understand` on the backend: the
 * newest thing available, degrading to something true rather than to nothing.
 */
export function keyPoint(
  result: Pick<RespondResult, "classification"> & { headline?: string | null },
  openGaps: NodeGap[],
  verdictWord: string
): string {
  // 1. The Grader said it itself.
  const headline = result.headline;
  if (typeof headline === "string" && headline.trim()) return headline.trim();

  // 2a. THE VERDICT VETOES THE FRAME. An answer graded `understood` can still
  // leave a gap open — gaps close only by verification (M6/M7), so one opened by
  // an earlier attempt survives a later correct answer, and the node is reported
  // `partial` until it is checked. Composing level 2 here produced, live:
  //
  //   "Understood — you're working from: requests only supports two built-in
  //    auth classes and does not provide an extension point"
  //
  // on the answer that had just refuted exactly that, correctly. The frame
  // asserts a belief the learner demonstrably does not hold. What is true is
  // that something earlier is still unchecked, which is also what
  // `feedbackActions` now offers as the primary — one story, not two.
  if (result.classification === "understood" && openGaps.length > 0) {
    return t.lesson.keyPointUnverified(verdictWord, openGaps.length);
  }

  // 2b. The leading gap. Blocking first — a blocking gap is by definition the one
  // standing between the learner and the objective, so it is the one to lead with.
  const leading = openGaps.find((g) => g.blocking) ?? openGaps[0];
  if (leading?.claim) return t.lesson.keyPoint(verdictWord, leading.claim);

  // 3. Nothing to compose from.
  return verdictWord;
}

/**
 * What the system did about it, as ONE line.
 *
 * §3a's second question. `retaught`, `pruned` and the three warm-up outcomes were
 * five separate conditional lines that could stack, all describing the same event
 * from different angles — which is a good part of why the feedback state read as
 * busy. They are ordered here by how much they changed the journey, and the first
 * that applies is the only one said.
 *
 * Nothing is lost by choosing: each of these is also visible in the journey itself.
 * A re-taught stop shows its new prose, a pruned journey is shorter in the rail, and
 * an inserted warm-up appears in the route as a stop marked "added after confusion".
 * The line is a courtesy that names the change; it was never the record of it.
 */
export function consequenceLine(result: RespondResult): string | null {
  const adaptation = result.adaptation;

  // Structural changes first: these altered the journey, not just this stop.
  if (adaptation?.kind === "prerequisite" || result.mutation?.kind === "prerequisite") {
    if (result.mutation?.kind === "prerequisite") return t.lesson.consequenceWarmUpAdded;
    if (result.mutation?.reason === "prerequisite_exists") return t.lesson.consequenceWarmUpExists;
    return t.lesson.consequenceWarmUpUnavailable;
  }

  if (typeof adaptation?.pruned === "number" && adaptation.pruned > 0) {
    return t.lesson.consequencePruned(adaptation.pruned);
  }

  // The lesson itself was rewritten — real, but the smallest of the three, and the
  // learner is about to read the new version anyway.
  if (adaptation?.retaught) return t.lesson.consequenceRetaught;

  return null;
}
