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
 *    Collapse — **unless this answer changed them.** The key point already leads
 *    with the blocking gap's claim, so a standing list underneath is the same
 *    information at length and the brief's counter keeps it one click away. But a
 *    gap that has just been OPENED is not superseded information, it is the
 *    consequence of the thing the learner just did, and collapsing it hid the
 *    system's conclusion about them behind a number. So: `gapsJustChanged` opens
 *    the block for exactly one verdict. Gaps also stay OPEN in `STUDY`, because
 *    there they are what the learner is answering about.
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
 * answered — and every other phase is two, or three on the one verdict that
 * changed the ledger.
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
  /**
   * Explanations a re-teach replaced, grouped behind one disclosure.
   *
   * Absent unless the caller passes a count, which is how the single canvas stays
   * exactly as it was: `next` passes nothing and gets nothing. The group belongs to
   * the surface split — it is R3's third mitigation, and R3 is about Lesson being a
   * surface of its own — so it is not something `next` was ever missing.
   */
  earlier: BlockState;
}

export interface ViewInput {
  phase: LessonPhase;
  /**
   * How many places in the code this unit is anchored on. Zero means there is
   * nothing to link to and the block cannot render; one is still worth showing.
   *
   * A count rather than the old `multiAnchor` boolean: the label depends on it
   * too — one place is not "a path crossing several places" — so a boolean was
   * throwing away the number the renderer needed anyway.
   */
  locationCount: number;
  /** Gaps still outstanding. Decides whether the block is worth OPENING. */
  openGapCount: number;
  /**
   * Every gap on the stop, settled ones included. Decides whether the block
   * EXISTS — which is a different question, and keying both off the open count
   * is what used to delete the whole ledger the moment the last gap was cleared.
   * Success made the record of the success disappear. Omit and it falls back to
   * the open count, which is the pre-ledger behaviour.
   */
  gapCount?: number;
  attemptCount: number;
  /**
   * The answer that just landed CHANGED this stop's ledger — it opened a gap, or
   * it closed one.
   *
   * The one thing that can open the gap block outside `STUDY`, and the reason is
   * that a collapsed disclosure is the wrong place for a consequence the learner
   * has not seen yet. Reported from a real session: an answer opened two gaps,
   * "What you got wrong here" stayed collapsed behind a count, and the learner
   * moved on without ever reading what the system had concluded about them.
   *
   * Deliberately narrower than "there are gaps here". A stop with three
   * long-standing open gaps and a verdict about something else should not
   * re-expand the ledger on every answer — that is the accumulation §3a exists
   * to prevent, and it would train the learner to ignore the block that matters
   * most on the one occasion it does. This opens for CHANGE, and change is a
   * fact about the last answer, not about the stop.
   */
  gapsJustChanged?: boolean;
  /** The reveal is unlocked — a graded answer exists, or this is a revisit. */
  revealed: boolean;
  /** This lesson actually has a withheld explanation to show. */
  hasReveal: boolean;
  /** How many explanations a re-teach has replaced. Omit for the single canvas. */
  supersededCount?: number;
}

export function lessonBlocks({
  phase,
  locationCount,
  openGapCount,
  gapCount,
  attemptCount,
  gapsJustChanged = false,
  revealed,
  hasReveal,
  supersededCount = 0,
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
    // WHERE THIS LIVES IN THE CODE, on every unit that has a file.
    //
    // This was `absent` for anything but a multi-anchor unit, which meant that on
    // the graphs most units are — one anchor, or none and only the display
    // projection — the list never appeared at all. "Almost never" is not a
    // disclosure decision, it is an accident of the data.
    //
    // A DISCLOSURE, never open. Opening it in STUDY was tried and reverted the
    // same hour: it takes STUDY to five open blocks, which is exactly the crowding
    // §3a exists to prevent, and the older reasoning still stands — L3 already puts
    // the same location in the brief, so an open list is the third place on screen
    // saying where this unit lives. Collapsed it is one labelled row and one click.
    tracePath: locationCount === 0 ? "absent" : "collapsed",

    // Present whenever the stop has a ledger AT ALL; open only where the gaps
    // are the subject and something is still outstanding.
    //
    // The two counts answer two questions. A stop where every gap is settled
    // still has a record worth keeping — "you got these wrong and then cleared
    // them" is the one place the learner sees their own repair — so it stays,
    // collapsed, as the record it now is. A stop that never had a gap has
    // nothing to collapse.
    gaps:
      (gapCount ?? openGapCount) === 0
        ? "absent"
        : (phase === "STUDY" && openGapCount > 0) || gapsJustChanged
          ? "open"
          : "collapsed",

    // A record, always consulted rather than read. The count lives in the brief.
    attempts: attemptCount === 0 ? "absent" : "collapsed",

    // The composer: exactly one, and only in the phases that own a question.
    question: asking ? "open" : "absent",

    // The verdict card: exactly one, and only in the phases that own a report.
    feedback: reporting ? "open" : "absent",

    // Earned, and open once earned — including on a revisit, where the learner is
    // reading rather than being tested.
    reveal: !hasReveal || !revealed ? "absent" : "open",

    // Never open, in any phase. The versions that were replaced are evidence of
    // how the learner's understanding moved, not material to read now — and
    // expanding them is precisely how Lesson would become the accumulating
    // document R3 warns about.
    earlier: supersededCount === 0 ? "absent" : "collapsed",
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
