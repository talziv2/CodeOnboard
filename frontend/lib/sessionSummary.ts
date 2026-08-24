import type { SessionSummary } from "@/lib/api";

/** `owner/name`, which is how people say which repository they mean. */
export function repoLabel(repoUrl: string): string {
  return repoUrl
    .replace(/^https?:\/\/github\.com\//, "")
    .replace(/\.git$/, "")
    .replace(/\/$/, "");
}

/**
 * What to call this session on a card.
 *
 * The stored title first — the migration derived one from the goal, and the
 * learner may have renamed it since. Then the goal's own words, then the
 * repository. Never an empty heading: a card with no name is a card you cannot
 * pick out of a list.
 */
export function sessionTitle(session: SessionSummary): string {
  const stored = (session.title ?? "").trim();
  if (stored) return stored;
  const focus = (session.goal?.focus_area ?? session.goal?.primary_goal ?? "").trim();
  if (focus) return focus.charAt(0).toUpperCase() + focus.slice(1);
  return repoLabel(session.repo_url);
}

/**
 * "2 hours ago", "Aug 18" — the answer to "when was I last here".
 *
 * Switches to an absolute date past a week, because "23 days ago" is arithmetic
 * the reader has to do and "Aug 18" is a fact they can recognise.
 *
 * Returns null rather than a guess when there is no timestamp, so the caller can
 * omit the line instead of printing something like "just now" about a session
 * whose age is unknown.
 */
export function relativeTime(iso: string | null, now: Date = new Date()): string | null {
  if (!iso) return null;
  // THE BACKEND WRITES UTC WITHOUT SAYING SO.
  //
  // `updated_at` comes from SQLite's `strftime('%Y-%m-%d %H:%M:%f','now')`,
  // which is UTC — but carries no timezone marker, and `new Date()` reads a
  // marker-less string as LOCAL time. Left alone, every timestamp is wrong by
  // the reader's offset: a session touched three hours ago reads as six, or as
  // "just now" for someone west of UTC because the date lands in the future.
  //
  // So a string with no offset is treated as UTC, which is what it is. Strings
  // that DO carry one (`last_active_at`, written as ISO-8601 by the account
  // layer) are left exactly as they are.
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso.trim());
  const normalised = iso.trim().replace(" ", "T") + (hasZone ? "" : "Z");
  const then = new Date(normalised);
  if (Number.isNaN(then.getTime())) return null;

  const seconds = Math.max(0, (now.getTime() - then.getTime()) / 1000);
  if (seconds < 90) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  if (days <= 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  return then.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
