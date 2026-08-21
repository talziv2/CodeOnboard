import type { LessonPhase } from "@/lib/lessonPhase";
import type { BlockState, LessonBlocks } from "@/lib/lessonView";

/**
 * Which surface each block belongs to.
 *
 * `lessonView` answered *what weight* a block carries in a given phase. This adds
 * the second axis — *which surface it lives on* — and nothing else. The state rules
 * are untouched on purpose (`ui-surfaces.md` §6): if placing blocks in two surfaces
 * also changed when they open, a regression in either would be indistinguishable
 * from a regression in the other.
 *
 * The two surfaces are separated by PURPOSE, which is the whole point of the
 * revision:
 *
 *   Lesson         "what should I read now?"
 *   Understanding  "what have I shown, what am I missing, what should I do now?"
 *
 * L4 collapsed what was superseded and measurably improved the canvas — 1565px to
 * 1127px, two primaries to one — and manual inspection still found the session
 * heavy. §1's diagnosis is that collapse and separation are ORTHOGONAL: collapse
 * solves accumulation within a purpose and does nothing about mixing between
 * purposes. L4 removed the accumulation and left the mixing. This is the mixing.
 *
 * WHY A TOTAL RECORD AND NOT A FUNCTION WITH A DEFAULT. `Record<BlockName, Surface>`
 * over `keyof LessonBlocks` makes it a type error to add a block to the view model
 * without saying where it goes. S5 adds Lesson's adaptive sections, and the failure
 * mode worth designing out is a block that renders in neither surface — invisible,
 * with nothing to notice it. The compiler notices instead.
 */
export type Surface = "lesson" | "understanding";

export type BlockName = keyof LessonBlocks;

/**
 * The surface that OWNS each block — where it is expanded, and where its state
 * from `lessonBlocks` applies as written.
 */
export const SURFACE_OF: Record<BlockName, Surface> = {
  // ── Lesson: the material to read ───────────────────────────────────────────
  /** The prose to read before answering. Owned here, and ONLY here. */
  setup: "lesson",
  /** Where the unit lives in the code. Owned here; mirrored — see `MIRRORED`. */
  tracePath: "lesson",
  /** The explanation, once earned. The newest thing Lesson has to offer. */
  reveal: "lesson",
  /**
   * The explanations a re-teach replaced. Material, therefore Lesson — and the
   * exhaustive `Record` above is what forced this line to exist: adding the block
   * to the view model failed the build until it was given a surface, which is the
   * whole reason the map is total rather than a function with a default.
   */
  earlier: "lesson",

  // ── Understanding: what the learner has shown, and what is outstanding ─────
  /** The question and composer — the act of being examined, not of reading. */
  question: "understanding",
  /** The verdict: key point, rationale, consequence, actions. */
  feedback: "understanding",
  /**
   * Named misconceptions and their status — open, cleared, set aside — with the
   * per-gap controls for clearing one or setting it aside. Understanding's,
   * because a claim the learner made is evidence about them, not material.
   */
  gaps: "understanding",
  /** Previously graded answers. Evidence about the learner. */
  attempts: "understanding",
};

/**
 * The blocks that appear in BOTH surfaces, and the surface each is mirrored INTO.
 *
 * §1's reason 3 is the durable cost of the split: **answers here are grounded, and
 * grounding means referring.** Answering needs the objective, the prose and the
 * code. The objective is in the brief, above both tabs; the code column was never
 * in a tab.
 *
 * WHAT IS MIRRORED, AND WHY IT IS THE LINKS AND NOT THE PROSE. The setup was
 * mirrored here once and was removed: it is the single longest thing on the page,
 * and duplicating it put the material into both surfaces at once — the accumulation
 * L4 removed, reintroduced sideways. The code locations are the opposite shape. A
 * handful of `file · symbol · lines` links is small, and it is a *reference* rather
 * than material: mid-answer the question it settles is "which code am I being asked
 * about", which is exactly what a learner should not have to change tabs to find.
 *
 * So the prose stays Lesson's and the learner goes there to read it; the links are
 * consultable from where the answering happens.
 *
 * A MIRROR IS NEVER EXPANDED. `surfaceBlocks` enforces it rather than trusting the
 * caller. The owning surface is where a block is read; the mirror is where it is
 * consulted.
 *
 * Deliberately a map rather than a boolean on the block: duplication across surfaces
 * is a cost, so it is enumerated in one place where adding to it is a visible
 * decision.
 */
export const MIRRORED: Partial<Record<BlockName, Surface>> = {
  tracePath: "understanding",
};

const ALL_BLOCKS = Object.keys(SURFACE_OF) as BlockName[];

export function surfaceOf(block: BlockName): Surface {
  return SURFACE_OF[block];
}

/**
 * What one surface renders, and at what weight.
 *
 * Owned blocks keep the state `lessonBlocks` gave them. A block mirrored into this
 * surface arrives `collapsed` — or `absent`, if it is absent everywhere: a mirror
 * cannot show what does not exist.
 */
export function surfaceBlocks(
  blocks: LessonBlocks,
  surface: Surface
): Partial<Record<BlockName, BlockState>> {
  const out: Partial<Record<BlockName, BlockState>> = {};
  for (const block of ALL_BLOCKS) {
    if (SURFACE_OF[block] === surface) {
      out[block] =
        block === "setup" && surface === "lesson"
          ? setupInLesson(blocks)
          : block === "question" && surface === "understanding"
            ? questionInUnderstanding(blocks)
            : blocks[block];
    } else if (MIRRORED[block] === surface) {
      out[block] = blocks[block] === "absent" ? "absent" : "collapsed";
    }
  }
  return out;
}

/**
 * The setup's weight **within Lesson**, which is not the same question the single
 * canvas was answering.
 *
 * `lessonBlocks` opens the setup in `STUDY` and collapses it everywhere else, and
 * that was right for one column: a verdict arrived, became the new primary, and the
 * longest thing on the page stepped back for it. In a surface split it is wrong,
 * because **a verdict is not newer material — it is not even on this surface.**
 *
 * Left alone, Lesson had NOTHING expanded in `FEEDBACK` on any lesson with no
 * withheld explanation: setup collapsed, trace path collapsed, reveal absent. A tab
 * that reads as broken, and a real hole the split creates rather than inherits. The
 * two R2 gates below caught it.
 *
 * §4's Lesson table already states the rule this surface needs — the setup is open
 * *"when no newer material exists"* and collapses *"superseded by a re-teach or a
 * newer section"*. Newer material in Lesson means the explanation, so:
 *
 *   reveal open  →  the explanation is the newest thing; the prose is a disclosure
 *   otherwise    →  the prose IS the material, whatever phase Understanding is in
 *
 * DELIBERATELY NOT A CHANGE TO `lessonBlocks`. That function serves the `next` path
 * too, which stays live behind its own flag for the comparison, and this rule is
 * only meaningful once there are two surfaces for a thing to be superseded *within*.
 * Keeping it here is what lets the two paths be wrong independently.
 *
 * The consequence is a stronger guarantee than R3 asks for: Lesson has **exactly
 * one** expanded section in every phase, which leaves S5's adaptive section room to
 * be the second without approaching the cap.
 */
function setupInLesson(blocks: LessonBlocks): BlockState {
  if (blocks.setup === "absent") return "absent";
  return blocks.reveal === "open" ? "collapsed" : "open";
}

/**
 * The question's weight **within Understanding**, which is the other place the
 * single canvas was answering a different question.
 *
 * `lessonBlocks` makes the question `absent` once a verdict exists, and that was
 * right for one column: the composer had to go — L4 asserts it — and the verdict
 * became the artifact in its place, directly below the prompt the learner had just
 * been reading. Nothing was lost, because the question was still on screen a moment
 * ago and the page had not moved.
 *
 * On a surface it is wrong. Understanding in `FEEDBACK` showed a verdict, three
 * collapsed disclosures, and no sign of what had been asked — so "what have I
 * shown?" was answerable and "shown about WHAT?" was not, on the one surface whose
 * whole purpose is the first question.
 *
 * §4's Understanding table already specifies the fix: the current question is open
 * while it is the live artifact and **collapsed when a verdict supersedes it**, not
 * absent. So:
 *
 *   question open      →  open. The composer, and the only composer.
 *   verdict up instead →  collapsed. The prompt TEXT, with no composer in it.
 *   neither            →  absent.
 *
 * THE COMPOSER IS NOT WHAT COLLAPSES. `LessonCanvas` renders a separate
 * prompt-only node in the collapsed case, because re-rendering the composer inside
 * a disclosure would put a second textarea in the DOM and break the one-composer
 * invariant — the thing L4 exists to guarantee. Collapsed here means "the question,
 * to re-read", never "the question, to answer again".
 *
 * Deliberately not a change to `lessonBlocks`, for the same reason as
 * `setupInLesson`: `next` keeps its own behaviour, and the two paths stay
 * independently wrong.
 */
function questionInUnderstanding(blocks: LessonBlocks): BlockState {
  if (blocks.question !== "absent") return blocks.question;
  return blocks.feedback === "open" ? "collapsed" : "absent";
}

/** How many blocks one surface has expanded. The R3 gate reads this. */
export function openCountIn(blocks: LessonBlocks, surface: Surface): number {
  return Object.values(surfaceBlocks(blocks, surface)).filter((s) => s === "open").length;
}

/**
 * The blocks the learner's CURRENT STATE is about, per phase.
 *
 * This is the never-nest rule (§4) written as data, and the R2 gate reads it.
 * Hiding behind a tab and hiding behind a disclosure compound to "where is
 * anything?", so material about the current state is expanded in its own surface;
 * only superseded material is allowed to be behind both.
 *
 * Understanding always owns exactly one of these, and they are mutually exclusive
 * by construction in `lessonBlocks` — `question` in the phases that own a question,
 * `feedback` in the phases that own a report. Lesson owns `reveal` once it is
 * unlocked, because the explanation is then the newest thing it has, and the setup
 * until then — which is exactly the supersession `setupInLesson` implements, so the
 * two cannot disagree about which of them is live.
 */
export function liveArtifacts(phase: LessonPhase, blocks: LessonBlocks): BlockName[] {
  const live: BlockName[] = [];

  // Understanding's live artifact.
  live.push(phase === "STUDY" || phase === "VERIFY" ? "question" : "feedback");

  // Lesson's.
  live.push(blocks.reveal === "open" ? "reveal" : "setup");

  return live.filter((b) => blocks[b] !== "absent");
}
