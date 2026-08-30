"use client";

import { useRouter } from "next/navigation";
import Button from "@/components/ui/Button";
import { t } from "@/lib/strings";

/**
 * The way out of a session, and back to the learner's own list of them.
 *
 * A session used to be a room with no door. Everything in the header's trailing
 * controls does something TO the session — adjusts its scope, restores it,
 * re-plans it, ends it — and the only navigation that existed was the browser's
 * back button and the completion screen's foot-of-page link. Someone mid-journey
 * who wanted to look at their other sessions had to guess.
 *
 * It leads the header rather than joining the controls, for two reasons. The
 * trailing group is destructive-adjacent — `Start over`, `Rebuild`, `Finish` all
 * live one press away in `SessionMenu` — and leaving is none of those things: it
 * changes NOTHING about the session, which is exactly why it must not be filed
 * with the actions that do. And the leading edge is where a way back belongs;
 * `/new` already puts the same words there, in the same `chrome` weight, so this
 * reuses a convention rather than inventing one.
 *
 * `chrome`, deliberately: mono, `graphite`, signal only on hover. The learning
 * actions are the primaries in the lesson column, and a way out that competed
 * with them would be a way out that got pressed by accident.
 *
 * The LABEL collapses under `sm`, not the control. The header already does this
 * with its two progress measures — the numbers stay, the uppercase eyebrows come
 * back on hover — and the same rule applies here: the arrow keeps its place in
 * the row, and `aria-label` plus `title` carry the full sentence for anyone who
 * sees only the arrow or hears only the name.
 */
export default function DashboardLink({ className = "" }: { className?: string }) {
  const router = useRouter();

  return (
    <Button
      variant="chrome"
      size="xs"
      // `Button` sets no default, and an unqualified <button> is a submit. The
      // header is not a form today, which is exactly why this is easy to get
      // wrong later — it is pinned here rather than relied on.
      type="button"
      // `push`, not `replace`: the session stays in history, and nothing about it
      // is touched. This is navigation and only navigation — no reset, no rebuild,
      // no sign-out, and the row on the dashboard is the same row it was.
      onClick={() => router.push("/sessions")}
      aria-label={t.dashboard.backToDashboard}
      title={t.dashboard.backToDashboard}
      className={`flex shrink-0 items-center gap-1.5 ${className}`}
    >
      <BackArrow />
      <span className="hidden sm:inline">{t.dashboard.mySessions}</span>
    </Button>
  );
}

function BackArrow() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className="h-[0.8rem] w-[0.8rem] shrink-0 fill-none stroke-current stroke-[1.3]"
    >
      <path d="M13 8H3.5" strokeLinecap="round" />
      <path d="M7 3.5 L2.5 8 L7 12.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
