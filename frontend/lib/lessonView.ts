import type { LessonPhase } from "@/lib/lessonPhase";

/**
 * Which blocks the canvas shows, and at what weight, for a given phase.
 *
 * This is where §3a is answered. The complaint was that the feedback state is too
 * busy, and the count behind it was sixteen conditional sub-blocks inside the
 * feedback branch plus five other blocks already on screen around it — the setup
 * prose, the trace path, the gap list, the attempt history, and the reveal with two
 * callouts. Restyling cannot reduce that. Deciding what is PRIMARY can.
 *
 * The rule is one sentence: **the canvas shows one primary artifact per phase, and
 * everything the phase has superseded collapses to a disclosure.** Superseded does
 * not mean gone — every block stays reachable, which is what makes this safe to be
 * wrong about.
 *
 * §3a's five questions, answered:
 *
 * 1. *After a correct answer, what should be on screen beyond the verdict and Next?*
 *    The verdict with its key point, the rationale, and the explanation — which is
 *    the payoff for having answered and would be perverse to withhold at the one
 *    moment it is earned. Not the setup prose, not the trace path, not the history.
 *
 * 2. *Do the adaptation notices belong to the feedback or to A1's channel?*
 *    To the feedback, but as ONE consequence line rather than three stacked
 *    notices. `retaught`, `pruned` and the warm-up status were three separate
 *    conditional lines saying three things about the same event. A1 can give them a
 *    channel later; what fixed the crowding is saying it once.
 *
 * 3. *Should gaps stay visible during feedback, or collapse to the brief's counter?*
 *    Collapse. The key point already leads with the blocking gap's claim, so the
 *    list underneath was the same information at length, and the brief's counter
 *    keeps it one click away. Gaps stay OPEN in `STUDY`, because there they are not
 *    superseded — they are what the learner is answering about.
 *
 * 4. *Do `takeaway` and `ownership` belong beside the explanation?*
 *    Yes; they are about the explanation, and they travel with it. What is dropped
 *    is the second `Key point` above the reveal that `ui-concept.md` §10.4 floated:
 *    two places to feel finished is the shallow-skipping risk this design exists to
 *    avoid.
 *
 * 5. *Is the attempt history ever wanted during feedback?*
 *    No. It is a record, and a record is something you consult. Collapsed in every
 *    phase, with the count in the brief.
 *
 * Kept as a pure function of the phase and a few counts, so the answer to "what is
 * on screen right now" is one thing to read and one thing to test — rather than
 * sixteen conditionals whose combined behaviour nobody can state.
 *
 * The count is the gate, and writing it as a test is what caught the first draft
 * leaving five blocks open in `STUDY` on a revisit. The worst case now is four —
 * setup, gaps, question and reveal, for someone returning to a stop they already
 * answered — and every other phase is two.
 */
export type BlockState = "open" | "collapsed" | "absent";

export interface LessonBlocks {
  /** The setup prose — what to read before answering. */
  setup: BlockState;
  /** The ordered walk through a multi-anchor unit. */
  tracePath: BlockState;
  /** Named gaps, with their per-gap set-aside control. */
  gaps: BlockState;
  /** Previously graded answers. */
  attempts: BlockState;
  /** The practice surface's question and composer. */
  question: BlockState;
  /** The verdict card. */
  feedback: BlockState;
  /** The explanation, with its takeaway and ownership callouts. */
  reveal: BlockState;
}

export interface ViewInput {
  phase: LessonPhase;
  /** More than one anchor: there is a trace path to show. */
  multiAnchor: boolean;
  openGapCount: number;
  attemptCount: number;
  /** The reveal is unlocked — a graded answer exists, or this is a revisit. */
  revealed: boolean;
  /** This lesson actually has a withheld explanation to show. */
  hasReveal: boolean;
}

export function lessonBlocks({
  phase,
  multiAnchor,
  openGapCount,
  attemptCount,
  revealed,
  hasReveal,
}: ViewInput): LessonBlocks {
  const asking = phase === "STUDY" || phase === "VERIFY";
  const reporting = phase === "FEEDBACK" || phase === "RESOLVED";

  return {
    // Open only while the learner is still working out their answer. Once a
    // verdict exists the prose has done its job, and it is the single longest
    // thing on the page.
    setup: phase === "STUDY" ? "open" : "collapsed",

    // Collapsed in EVERY phase, which the count forced and the nature of the thing
    // agrees with. It is a list of links, not prose — a disclosure is what a list
    // of links wants to be — and L3 already put the same anchors in the brief, so
    // open it was the third place the learner could read where this unit lives.
    // Leaving it open in STUDY put five blocks on screen at once on a revisit,
    // which is the crowding §3a is about wearing a different phase.
    tracePath: !multiAnchor ? "absent" : "collapsed",

    // Open where they are the subject, collapsed where the key point has already
    // named the leading one.
    gaps: openGapCount === 0 ? "absent" : phase === "STUDY" ? "open" : "collapsed",

    // A record, always consulted rather than read. The count lives in the brief.
    attempts: attemptCount === 0 ? "absent" : "collapsed",

    // The composer: exactly one, and only in the phases that own a question.
    question: asking ? "open" : "absent",

    // The verdict card: exactly one, and only in the phases that own a report.
    feedback: reporting ? "open" : "absent",

    // Earned, and open once earned — including on a revisit, where the learner is
    // reading rather than being tested.
    reveal: !hasReveal || !revealed ? "absent" : "open",
  };
}

/**
 * How many of the canvas's blocks are open at once.
 *
 * The number §3a was really about. Before this the feedback state had the setup,
 * the trace path, the gaps, the history and the reveal all open around the verdict
 * card; the gate is that the phase with the most open blocks is a small number, and
 * this is what the test asserts against.
 */
export function openCount(blocks: LessonBlocks): number {
  return Object.values(blocks).filter((s) => s === "open").length;
}
