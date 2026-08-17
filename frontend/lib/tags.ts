import type { UnderstandingState } from "@/lib/api";
import { t } from "@/lib/strings";

/**
 * The concept-tag vocabulary is shared by the Mentor, Teaching, Grader and
 * Reviewer agents. Each tag keeps one fixed hue everywhere it appears so the
 * colour becomes readable on its own after a couple of encounters.
 *
 * Tags and understanding states travel the wire as fixed keys — those values
 * are what the UI switches on, and `tagLabel` / `stateLabel` map them to the
 * wording shown.
 *
 * The hues themselves live in `app/globals.css`, not here: a chip is drawn with
 * an inline style rather than a class, and a literal hex in this module would be
 * the one thing on the page a theme could not re-tune. These functions return
 * variable references, so light and dark are a CSS concern throughout.
 */
export interface TagStyle {
  text: string;
  border: string;
  background: string;
}

const cssTag = (name: string): TagStyle => ({
  text: `var(--tag-${name}-text)`,
  border: `var(--tag-${name}-border)`,
  background: `var(--tag-${name}-bg)`,
});

const CANONICAL_TAGS = [
  "architecture",
  "flow",
  "extension_point",
  "risk",
  "test_coverage",
  "component",
  // A unit that connects several earlier ones and introduces no new code —
  // where the mental model consolidates rather than grows. Warm and distinct
  // from the six "here is a new thing" kinds, because it is the opposite.
  "synthesis",
] as const;

const TAG_STYLES: Record<string, TagStyle> = Object.fromEntries(
  CANONICAL_TAGS.map((tag) => [tag, cssTag(tag)])
);

const FREEFORM: TagStyle = cssTag("freeform");

/** Domain tags the Mentor invents (auth, retries, …) fall back to a neutral chip. */
export function tagStyle(tag: string): TagStyle {
  return TAG_STYLES[tag] ?? FREEFORM;
}

/**
 * Canonical tags have a curated label. Free-form domain tags are whatever the
 * Mentor invented, so they are shown as written, with underscores relaxed into
 * spaces.
 */
export function tagLabel(tag: string): string {
  return t.tags[tag] ?? tag.replace(/_/g, " ");
}

/**
 * True for the shared vocabulary the Mentor, Teaching, Grader and Reviewer all
 * speak. Everything else is a free-form domain tag — a topic rather than a kind
 * of understanding, so aggregate views keep the two apart.
 */
export function isCanonicalTag(tag: string): boolean {
  return tag in TAG_STYLES;
}

// --- understanding state ---------------------------------------------------

export interface StateStyle {
  /** Ring colour. */
  stroke: string;
  /** Fill treatment — shape carries state so colour isn't the only channel. */
  fill: string;
}

export const STATE_STYLES: Record<UnderstandingState, StateStyle> = {
  understood: { stroke: "var(--color-jade)", fill: "var(--color-jade)" },
  partial: {
    stroke: "var(--color-brass)",
    fill: "linear-gradient(90deg,var(--color-brass) 50%,transparent 50%)",
  },
  failed: { stroke: "var(--color-rust)", fill: "transparent" },
  not_started: { stroke: "var(--color-graphite)", fill: "transparent" },
};

export function stateStyle(state: UnderstandingState): StateStyle {
  return STATE_STYLES[state] ?? STATE_STYLES.not_started;
}

export function stateLabel(state: UnderstandingState): string {
  return t.states[state] ?? state;
}

// --- the four understanding classes (M3a.1) --------------------------------
//
// Reuses the existing state palette deliberately: `recovered` is jade like
// `strength` because both are demonstrated understanding, and the difference
// between them is a fact about the ROUTE there, not about how well it is known.
// Rendering recovery in the failure colour is the very mistake this milestone
// removes.

import type { UnderstandingClass } from "@/lib/api";

export const UNDERSTANDING_STYLES: Record<UnderstandingClass, StateStyle> = {
  strength: { stroke: "var(--color-jade)", fill: "var(--color-jade)" },
  recovered: {
    stroke: "var(--color-jade)",
    // Half-filled: demonstrated, and it took more than one pass to get there.
    fill: "linear-gradient(90deg,var(--color-jade) 50%,transparent 50%)",
  },
  unresolved: { stroke: "var(--color-rust)", fill: "transparent" },
  insufficient: { stroke: "var(--color-graphite)", fill: "transparent" },
};

export function understandingStyle(state: UnderstandingClass): StateStyle {
  return UNDERSTANDING_STYLES[state] ?? UNDERSTANDING_STYLES.insufficient;
}

export function understandingLabel(state: UnderstandingClass): string {
  return t.map.understanding[state] ?? state;
}

/** Display order: demonstrated first, unknown last. */
export const UNDERSTANDING_ORDER: UnderstandingClass[] = [
  "strength",
  "recovered",
  "unresolved",
  "insufficient",
];

export const STATE_ORDER: UnderstandingState[] = [
  "understood",
  "partial",
  "failed",
  "not_started",
];
