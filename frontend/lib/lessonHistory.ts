import type { Attempt } from "@/lib/api";

/**
 * The explanations a re-teach replaced, oldest first.
 *
 * ── Why this exists ───────────────────────────────────────────────────────────
 *
 * R3 is the user's own warning: **Lesson must not become an accumulating
 * document.** Three mitigations were promised. Two are already true — a re-teach
 * REPLACES rather than appends (`teaching_respond.reteach` assigns
 * `cached_lesson` directly), and at most one section is expanded as new. This is
 * the third: the versions that were replaced are still reachable, grouped behind
 * one always-collapsed disclosure, rather than either stacked on the page or lost.
 *
 * Losing them is not a neutral option. A re-teach happens because the learner
 * misunderstood, and the prose that misled them is half of how their understanding
 * moved; the backend keeps it for exactly that reason (`superseded_lesson`, M2).
 * Stacking them is the other failure: three re-teaches on one stop and Lesson is
 * four explanations long, which is the document R3 is about.
 *
 * So: reachable, counted, and never expanded.
 *
 * ── What counts ───────────────────────────────────────────────────────────────
 *
 * Only attempts whose `response` actually carries a superseded lesson. A re-teach
 * that failed (`retaught: false`) replaced nothing and has nothing to show, and a
 * hint or follow-up never touched the prose at all.
 *
 * Verification attempts are excluded, and not merely absent: a verification is a
 * question about one gap, it never re-teaches, and pooling it here would put an
 * entry in the list with no explanation behind it.
 */
export interface SupersededExplanation {
  /** Where it sits in the sequence, 1 = the first version the learner saw. */
  version: number;
  /** The prose as it was. Either half may be missing on older records. */
  setup: string | null;
  reveal: string | null;
  /** The answer that caused it to be replaced — the reason this version went. */
  answer: string;
  at: string;
}

export function supersededExplanations(attempts: Attempt[]): SupersededExplanation[] {
  const out: SupersededExplanation[] = [];
  for (const attempt of attempts) {
    if ((attempt.kind ?? "assessment") === "verification") continue;
    const previous = attempt.response?.superseded_lesson;
    if (!previous) continue;
    const setup = previous.setup ?? previous.walkthrough ?? null;
    const reveal = previous.reveal ?? null;
    // Nothing to read is nothing to offer. An entry whose disclosure opens on
    // emptiness is worse than one fewer entry.
    if (!setup && !reveal) continue;
    out.push({
      version: out.length + 1,
      setup,
      reveal,
      answer: attempt.answer,
      at: attempt.response?.at ?? attempt.at,
    });
  }
  return out;
}

/**
 * Was the material the learner is looking at produced by their last answer?
 *
 * What the `new` marking is for. Reading `attempts` rather than the live grading
 * result on purpose: it survives a reload, and the question the learner asks on
 * arriving at Lesson — "is this different from what I read before?" — does not stop
 * being worth answering because the page was refreshed.
 *
 * The LAST attempt only. An earlier re-teach is not news; its output is what the
 * learner has been reading since.
 */
export function materialIsNew(attempts: Attempt[]): boolean {
  const assessments = attempts.filter((a) => (a.kind ?? "assessment") !== "verification");
  const last = assessments[assessments.length - 1];
  return last?.response?.retaught === true;
}
