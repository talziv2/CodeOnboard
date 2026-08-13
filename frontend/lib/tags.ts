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
 */
export interface TagStyle {
  text: string;
  border: string;
  background: string;
}

const TAG_STYLES: Record<string, TagStyle> = {
  architecture: { text: "#8fb6d9", border: "#33506b", background: "rgba(143,182,217,0.09)" },
  flow: { text: "#7fcbb8", border: "#2e5f55", background: "rgba(127,203,184,0.09)" },
  extension_point: { text: "#c7a0dc", border: "#543e63", background: "rgba(199,160,220,0.09)" },
  risk: { text: "#d4634f", border: "#6b2f26", background: "rgba(212,99,79,0.10)" },
  test_coverage: { text: "#d9a441", border: "#6b5220", background: "rgba(217,164,65,0.09)" },
  component: { text: "#7b8d99", border: "#24333d", background: "rgba(123,141,153,0.08)" },
};

const FREEFORM: TagStyle = {
  text: "#7b8d99",
  border: "#24333d",
  background: "rgba(123,141,153,0.06)",
};

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
  understood: { stroke: "#4fb286", fill: "#4fb286" },
  partial: { stroke: "#d9a441", fill: "linear-gradient(90deg,#d9a441 50%,transparent 50%)" },
  failed: { stroke: "#d4634f", fill: "transparent" },
  not_started: { stroke: "#7b8d99", fill: "transparent" },
};

export function stateStyle(state: UnderstandingState): StateStyle {
  return STATE_STYLES[state] ?? STATE_STYLES.not_started;
}

export function stateLabel(state: UnderstandingState): string {
  return t.states[state] ?? state;
}

export const STATE_ORDER: UnderstandingState[] = [
  "understood",
  "partial",
  "failed",
  "not_started",
];
