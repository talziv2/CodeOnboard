import type { BlockName } from "@/lib/lessonSurfaces";

/**
 * The lesson's attention markers, in one table.
 *
 * ── What these are, and what they are NOT ─────────────────────────────────────
 *
 * A lesson screen is a column of mono eyebrows in one size and one colour, and
 * that uniformity is the problem: `BEFORE YOU ANSWER`, `WHAT YOU GOT WRONG HERE`
 * and `WHERE THIS LIVES IN THE CODE` are three different kinds of thing wearing
 * the same 11px uppercase label, so finding the one you want means reading all of
 * them. A glyph is the cheapest way to make a block identifiable before it is
 * read — and, unlike colour, it survives this palette being fully semantic:
 * signal, jade, brass and rust are all spoken for.
 *
 * They are DECORATION, and three rules follow from that:
 *
 *   1. Every marker renders `aria-hidden` (see `components/ui/Marker.tsx`). The
 *      copy in `strings.ts` is the accessible name and stays the whole of it, so
 *      a screen reader hears "Before you answer" and not "open book, before you
 *      answer". That is also why the emoji are here and not in `strings.ts`: an
 *      emoji is not a piece of wording, and putting it there would have pushed it
 *      into every label's accessible name and every test's query string.
 *   2. A marker never carries information its label does not. Nothing is ever
 *      "the ✅ one" — delete this file and the screen still says everything it
 *      said before, less legibly.
 *   3. Repetition across roles is deliberate where the meaning repeats. ✅ marks
 *      a settled gap, a resolved gap and what a check closed, because those are
 *      one fact in three places, and a distinct glyph for each would invent a
 *      distinction the product does not make.
 *
 * ── EVERY GLYPH IS PICKED ON BOTH GROUNDS, AND MOST CANDIDATES FAIL ONE ──────
 *
 * An emoji is a small colour image with no `currentColor` to follow, so a theme
 * that swaps `ink` (#0a1014) for a near-white page (#e7eef3) is a theme that can
 * make one vanish — and it vanishes on ONE of the two, which is exactly the kind
 * of defect that survives being reviewed in whichever theme the reviewer happens
 * to use. Rendered side by side at 34px on both grounds and chosen from what
 * survived:
 *
 *   📖 open book      white pages, invisible on the light page      rejected → 📘
 *   📝 memo           white page, near-invisible on the light page  rejected → 📒
 *   🗒️ notepad        same failure                                  rejected
 *   📓 notebook       dark purple, lost on ink                       rejected
 *   🚏 bus stop       dark blue sign, lost on ink                    rejected → 🧭
 *   🔬 microscope     dark body, muddy on ink                        rejected → 🧪
 *
 * So the working rule for anything added here: a glyph that is mostly white or
 * mostly near-black is wrong whatever it depicts, and a saturated mid-tone —
 * blue, gold, green, red — is right. Add one and look at it in both themes; the
 * repository's own record is that a third of its defects were only visible on the
 * rendered page.
 *
 * ONE CAVEAT ON THAT LIST: it was read in **Segoe UI Emoji**, because that is
 * what Windows renders. The same code points are different artwork under Apple
 * Color Emoji and Noto Color Emoji, so the individual rejections above are a
 * judgement about one font's drawing of them. The rule they produced — pick a
 * saturated mid-tone, distrust anything mostly white or mostly black — is the part
 * that carries across, since it is about the artwork's value rather than its
 * shape. The emoji families themselves are named explicitly in the `body` rule in
 * `globals.css`, which is what stops a platform with none of them rendering tofu.
 *
 * ── Why a total `Record` for the blocks ──────────────────────────────────────
 *
 * `BLOCK_ICON` is keyed over `BlockName`, so adding a block to `lessonView`
 * without choosing a marker is a type error — the same device, and the same
 * reason, as `SURFACE_OF` in `lessonSurfaces.ts`: one unmarked block beside eight
 * marked ones reads as a rendering fault, and there is nothing on screen to
 * notice it by. The compiler notices instead.
 */

/**
 * The marker for a block where the block is drawn as a `Disclosure` — the
 * collapsed row `LessonCanvas` renders. The expanded forms carry their own, from
 * `LESSON_ICON` below, because a block and its collapsed row are drawn by
 * different components.
 *
 * `feedback` is the one entry that never reaches a disclosure: the block is
 * `open` or `absent`, and its live card is marked by the verdict instead
 * (`VERDICT_ICON`). It is not dead, though — the practice surface wears it on the
 * eyebrow while a verdict is up, which is the whole reason it is a report glyph
 * rather than a verdict one: repeating the tick on the frame around the card that
 * already says it would say the same thing twice a centimetre apart.
 */
export const BLOCK_ICON: Record<BlockName, string> = {
  setup: "📘",
  tracePath: "📍",
  reveal: "💡",
  earlier: "🗂️",
  question: "❓",
  feedback: "📊",
  gaps: "⚠️",
  attempts: "📒",
};

/**
 * The markers for everything in the lesson that is not a block: the callouts, the
 * sub-headings, the gap statuses, and the three things the practice surface can
 * be.
 *
 * Keyed by ROLE rather than by the copy it sits beside, so re-wording a label in
 * `strings.ts` cannot orphan a marker — and so the pairs that must not collide
 * sit next to each other. `hint` and `tracePath` are the pair that matters: both
 * mean "look over here", and one compass serving both would say nothing.
 */
export const LESSON_ICON = {
  /** A pre-B4 lesson's single body. Same role as `setup`, so the same marker. */
  walkthrough: "📘",
  /** One anchor rather than a path. Same role as `tracePath`. */
  codeLocation: "📍",
  takeaway: "🎯",
  ownership: "🔑",
  /**
   * The adaptation that offers a way into a question — a piece to start from.
   *
   * NOT a compass, though "a way in" wants one: `offRoute` has the better claim
   * on that glyph, because being off the route is literally a navigation fact,
   * and two compasses would have made the pair say nothing. This is the one
   * collision in the table that had to be resolved rather than allowed.
   */
  hint: "🧩",
  /** The adaptation that re-asks from another angle. */
  followup: "🔁",
  /** The lesson's own question, live in the practice surface. */
  question: "❓",
  /** A check on one named belief. */
  verification: "🧪",
  /** An open gap — blocking or merely worth knowing; the chip beside it says which. */
  gapOpen: "⚠️",
  /** Resolved: the learner answered a check on it. */
  gapResolved: "✅",
  /**
   * Ignored for now. NOT resolved, and the marker has to keep saying so — a
   * second ✅ here would blur the one distinction `GapList` exists to hold, so
   * this is a glyph about being parked rather than about being finished.
   */
  gapWaived: "💤",
  /** What a check closed. The same fact as `gapResolved`, said in the verdict card. */
  checkClosed: "✅",
  /** A re-teach rewrote this stop's material. */
  rewritten: "✨",
  /** The warm-up worked: a failure, then a warm-up, then an `understood`. */
  recovered: "🎉",
  /**
   * The learner did not walk here.
   *
   * A navigation glyph and deliberately not a warning one: jumping is allowed,
   * the notice reports movement and never judges it, and 🚩 or ⚠️ here would
   * contradict the copy it sits beside — the one thing `ArrivalNotice`'s wording
   * rule forbids.
   */
  offRoute: "🧭",
} as const;

/**
 * The glyph a verdict is spoken with, keyed by the Grader's classification.
 *
 * The sibling of `VERDICT_COLOR` in `lib/verdict.ts`, shaped the same way and for
 * the reason stated there: two places say a verdict — the attempt history and the
 * live feedback card — and one table is what stops them disagreeing about what
 * `partial` looks like.
 *
 * It lives HERE rather than beside the colour because every emoji in the lesson
 * belongs to one table; the cross-reference in `verdict.ts` keeps the pair
 * findable from either end.
 *
 * A classification this table does not know renders NO marker rather than a
 * placeholder — `Marker` returns null on an empty glyph. A new verdict word has
 * to read as neutral, which is the rule `NEUTRAL` already states for the colour.
 */
export const VERDICT_ICON: Record<string, string> = {
  understood: "✅",
  partial: "🟡",
  confused: "❌",
  /** The answer was about something else. Not a failure of understanding. */
  "off-topic": "↪️",
};

/**
 * The marker for an attempt-history row that is a CHECK.
 *
 * A check carries no classification by design, so it can take no verdict glyph.
 * It takes the one the practice surface wore while the check was live, which is
 * what makes the row recognisable later as the same event.
 */
export const CHECK_ICON = LESSON_ICON.verification;
