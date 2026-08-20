"use client";

import type { ReactNode } from "react";

/**
 * A block the phase has superseded: present, reachable, and not spending height.
 *
 * The unit of §3a's answer. The feedback state was crowded because every block
 * that had ever been relevant stayed at full weight, so "what matters now" had to
 * be found among five things that mattered a moment ago. A disclosure is how a
 * block steps back without leaving.
 *
 * `<details>` rather than a button and some state, for three reasons that all
 * matter here: it is open/closed without React holding the answer, it is
 * keyboard-operable and announced correctly with no ARIA of ours, and it survives
 * an environment that runs no animation frames — which several things in this app
 * do not. The same element the attempt cards already use.
 *
 * The summary says what is inside and how much of it, because a disclosure whose
 * label is just a noun makes the reader open it to find out whether they wanted
 * it. `count` is rendered when it is a number worth knowing — two gaps is
 * different from six — and omitted when the block is singular.
 */
export default function Disclosure({
  label,
  count,
  children,
  className = "",
}: {
  label: string;
  count?: number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <details className={`group rounded-card border border-rule bg-slab ${className}`}>
      <summary className="flex cursor-pointer list-none items-center gap-2.5 px-3 py-2">
        <Chevron />
        <span className="font-mono text-micro uppercase tracking-[0.13em] text-graphite transition group-hover:text-signal">
          {label}
        </span>
        {typeof count === "number" && (
          <span className="font-mono text-micro tabular-nums text-graphite">{count}</span>
        )}
      </summary>
      <div className="border-t border-rule px-3 py-3">{children}</div>
    </details>
  );
}

function Chevron() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 10 10"
      className="h-2.5 w-2.5 shrink-0 fill-none stroke-graphite stroke-[1.5] transition-transform group-open:rotate-90"
    >
      <path d="M3.5 1.5 L7 5 L3.5 8.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
