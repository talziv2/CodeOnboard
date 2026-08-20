"use client";

import type { SessionGraph } from "@/lib/api";
import { sessionLog } from "@/lib/sessionLog";
import SectionLabel from "@/components/ui/SectionLabel";
import { t } from "@/lib/strings";

/**
 * What the system did to this journey, and when.
 *
 * A1's third channel. The consequence line inside the verdict card says each of
 * these once, at the moment it happens; a learner who was reading something else,
 * or who resumed tomorrow, has no other way to find out that the route they are
 * walking is not the route they agreed to.
 *
 * Draws only. Every decision — which sources contribute, what each row says, what
 * order they come in — is in `lib/sessionLog.ts`, because a decision in a render
 * body is a decision nobody can test.
 *
 * ON THE MAP TAB, not in a menu. The map is already the session-level peer view of
 * the lesson, and this is session-level history; putting it behind a menu item
 * would make "what changed" something you have to suspect before you can find.
 */
export default function SessionLog({ graph }: { graph: SessionGraph }) {
  const entries = sessionLog(graph);

  return (
    <div className="flex flex-col gap-3">
      <SectionLabel>{t.log.label}</SectionLabel>

      {entries.length === 0 ? (
        /* Said rather than left blank: an empty region reads as something that
           failed to load, and "nothing has changed" is a fact worth having. */
        <p className="measure text-meta text-graphite">{t.log.empty}</p>
      ) : (
        <ol className="flex flex-col gap-2.5">
          {entries.map((entry, index) => {
            const say = t.log.kinds[entry.kind];
            if (!say) return null;
            return (
              <li
                key={`${entry.kind}-${entry.at}-${index}`}
                className="flex gap-2.5 text-meta"
              >
                <span
                  aria-hidden
                  className="mt-[calc(7rem/16)] h-1 w-1 shrink-0 rounded-full bg-signal-dim"
                />
                <span className="measure text-paper">{say(entry.count, entry.subject)}</span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
