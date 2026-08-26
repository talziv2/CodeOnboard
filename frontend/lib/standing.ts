import type { Disposition, GraphNode, UnderstandingClass } from "@/lib/api";
import { understandingStyle, type UnderstandingStyle } from "@/lib/tags";
import { t } from "@/lib/strings";

/**
 * How a stop should READ, from the four facts the server sends about it.
 *
 * ── Why this exists ───────────────────────────────────────────────────────────
 *
 * The pin rendered `understanding` alone, and `understanding` cannot answer the
 * question a learner actually asks of the rail — *"is there anything left for me
 * here?"* Two of its four values are ambiguous about exactly that:
 *
 *   `insufficient`  covers BOTH "never opened" and "answered, and the answer told
 *                   us nothing". The second is the commonest failure the system
 *                   sees: an `off-topic` answer is excluded from evidence by
 *                   `history.is_evidence`, so a stop the learner genuinely
 *                   attempted classifies identically to one they have never seen.
 *   `unresolved`    covers both "you are stuck here" and "you decided to move on".
 *
 * The missing bits are already on the wire and were simply not read: `disposition`
 * (what the learner DECIDED), `attempted` (did they try) and `visited` (did they
 * walk past it). This composes all four into the one value every surface renders
 * from.
 *
 * ── The encoding ──────────────────────────────────────────────────────────────
 *
 * Understanding and disposition are independent dimensions server-side and they
 * stay independent here — this is a projection for display, never a fifth
 * understanding state. Nothing in it can make a node look demonstrated that the
 * evidence does not, which is the M0 invariant: **a learner decision is not
 * evidence of understanding.** `demonstrated` is reachable from `understanding`
 * alone, and no disposition produces it.
 *
 *   standing        ring      dash?     bar?   means
 *   demonstrated    jade      solid     no     the evidence says they have it
 *   open            rust      solid     no     assessed, short of it, still live
 *   attempted       graphite  solid     no     they tried; it told us nothing
 *   untouched       graphite  dashed    no     nothing has happened here
 *   passed_by       graphite  solid     YES    reached, never answered, moved on
 *   set_aside       inherited inherited YES    not demonstrated, and they closed it
 *
 * TWO SHAPE CHANNELS, ONE BIT EACH, so neither depends on colour: the DASH says
 * "nothing has happened here" and the BAR says "the learner closed this". That
 * matters most for the pair the dash was introduced to separate in the first
 * place — `unresolved` and `insufficient` were an empty circle differing only in
 * hue — and it keeps that separation while adding the two cases above. Every
 * surface also names the standing in words, so nothing rests on either channel.
 *
 * `set_aside` keeps the ring it would otherwise have had rather than taking a
 * colour of its own. What the learner decided must not overwrite what the
 * evidence says: a stop set aside at `unresolved` and one set aside with no
 * evidence at all are different facts, and one colour for both would erase it.
 */
export type Standing =
  | "demonstrated"
  | "open"
  | "attempted"
  | "untouched"
  | "passed_by"
  | "set_aside";

/** The four server-sent facts this reads. Nothing else is consulted. */
export interface StandingInput {
  understanding?: UnderstandingClass;
  disposition?: Disposition;
  /** Has the learner answered this stop's own question at least once? */
  attempted?: boolean;
  /**
   * Has the learner advanced PAST this stop?
   *
   * Written by `/advance` and by an explicit `skip`, and by nothing else — so
   * unlike presence it is always a click. A refresh does not set it, scrolling
   * does not set it, and opening a lesson does not set it.
   *
   * It is read here for exactly one case, `passed_by`. Everywhere else the other
   * three facts already decide the answer, and `visited` would only ever agree
   * with them.
   */
  visited?: boolean;
}

/**
 * Dispositions that mean the learner closed the question here.
 *
 * Mirrors `understanding.SETTLING_DISPOSITIONS` server-side. Duplicated rather
 * than derived because the wire carries the value and not the set — and asserted
 * in `standing.test.ts` against the same four names, so a change on either side
 * that is not made on both fails a test rather than drifting.
 */
const SETTLED: Disposition[] = ["continued", "waived", "skipped", "asserted"];

const DEMONSTRATED: UnderstandingClass[] = ["strength", "recovered"];

export function standingOf({
  understanding,
  disposition,
  attempted,
  visited,
}: StandingInput): Standing {
  const state = understanding ?? "insufficient";

  // Demonstrated wins outright, and it is the reason the order matters. A learner
  // who set a stop aside and LATER demonstrated it must read as demonstrated —
  // `waive_remaining` survives a later answer by design, so the disposition is
  // still on the node while the evidence has moved past it.
  if (DEMONSTRATED.includes(state)) return "demonstrated";

  if (disposition && SETTLED.includes(disposition)) return "set_aside";

  if (state === "unresolved") return "open";

  // `insufficient`, and nobody has decided anything. The only remaining question
  // is whether they tried.
  if (attempted) return "attempted";

  /**
   * REACHED, NEVER ANSWERED, AND WALKED PAST.
   *
   * The one standing the wire could always support and nothing read. A learner
   * who arrives at a stop, does not answer, and moves on rendered EXACTLY like a
   * stop they had never opened: dashed grey, no bar, "nothing has happened
   * here". Two very different facts, and the honest one is the one the rail was
   * not showing.
   *
   * WHY IT IS NOT `set_aside`. `set_aside` is the disposition channel — a
   * decision the SERVER recorded — and the server deliberately records nothing
   * here: `continue_past` writes `continue` only where there is an unmet
   * objective plus at least one assessment, on the rule that a decision must be
   * about something (`learning-loop.md`). Advancing past a stop nobody answered
   * is about nothing, so no disposition is written, and inventing one in the
   * client would put a decision into a channel the server owns.
   *
   * So this is a DISPLAY standing over a fact the server already sends. It
   * carries the bar, because the learner did close the question by walking on,
   * and it keeps the grey ring, because no evidence was ever produced about
   * them — which is exactly the pair of claims the two shape channels exist to
   * keep separate.
   */
  if (visited) return "passed_by";

  return "untouched";
}

/** The same, read straight off a node. */
export function standingOfNode(node: GraphNode): Standing {
  return standingOf({
    understanding: node.understanding,
    disposition: node.disposition,
    attempted: node.attempted,
    visited: node.visited,
  });
}

export interface StandingStyle extends UnderstandingStyle {
  /** Draw the settled bar across the pin. */
  settled: boolean;
}

/**
 * How to draw a pin in this standing.
 *
 * Delegates the ring and fill to `understandingStyle` wherever the standing does
 * not override them, so the four understanding colours stay defined in exactly
 * one place and this cannot fork them.
 */
export function standingStyle(
  standing: Standing,
  understanding?: UnderstandingClass
): StandingStyle {
  const base = understandingStyle(understanding ?? "insufficient");
  switch (standing) {
    case "demonstrated":
    case "open":
      return { ...base, settled: false };
    // Something happened here and it told us nothing. SOLID, because the dash
    // means "nothing has happened" and something has.
    case "attempted":
      return { ...base, borderStyle: "solid", settled: false };
    // Reached and walked past with nothing shown. The BAR, because the learner
    // closed the question; the grey ring it inherits from `insufficient`,
    // because they produced no evidence either way and colouring it as a
    // shortfall would claim they got something wrong. Solid for the same reason
    // `attempted` is: being here at all took a click.
    case "passed_by":
      return { ...base, borderStyle: "solid", settled: true };
    case "untouched":
      return { ...base, settled: false };
    case "set_aside":
      // The ring it would have had if nobody had decided anything — which is
      // what keeps the evidence readable through the decision. Solid for the
      // same reason `attempted` is: a stop can only be set aside deliberately.
      return { ...base, borderStyle: "solid", settled: true };
  }
}

/**
 * What a stop's standing is CALLED.
 *
 * `understandingLabel` names the evidence class and stays the primary label
 * everywhere it already appears; this names the standing, which is the thing a
 * learner scanning the rail is actually asking about. Returns null where the
 * standing adds nothing the class has not already said — a demonstrated stop, and
 * one nobody has touched, both speak for themselves.
 */
export function standingLabel(standing: Standing): string | null {
  switch (standing) {
    case "attempted":
      return t.rail.attempted;
    case "passed_by":
      return t.rail.passedBy;
    case "set_aside":
      return t.rail.setAside;
    default:
      return null;
  }
}
