"use client";

import { useState } from "react";
import MapView from "@/components/MapView";
import type { SessionGraph } from "@/lib/api";
import Button from "@/components/ui/Button";
import { t } from "@/lib/strings";

/**
 * The end of the journey: what was covered, what is still unresolved, and the two
 * ways onward.
 *
 * Moved out of `LessonPanel` unchanged. It is reached from two places now — the
 * walk running out, and `Finish session` in the header menu — which is why the
 * `finished` flag that shows it lives on the page rather than in the panel.
 *
 * The one rule worth not losing: "another pass" lists what is STILL unresolved,
 * not everything the learner ever stumbled on. `weak_spot` is sticky, so keying
 * off it kept offering a second pass over units already mastered.
 *
 * ── THE WAY BACK ─────────────────────────────────────────────────────────────
 *
 * `Finish session early` is one unconfirmed click on a quiet link at the foot of
 * every lesson, and it landed here with no way out: the learner's only routes on
 * were a NEW session or the front door, both of which leave the one they were
 * mid-way through. Nothing had actually happened — the flag is client state and
 * no request is made — so the screen was showing an ending that had not occurred
 * and offering no way to un-see it.
 *
 * So THIS SCREEN IS THE CONFIRMATION, and `onResume` is what makes that true. It
 * is passed only when the learner CHOSE to stop: when the walk itself ran out
 * there is no stop to go back to, and a "keep going" button pointing at a
 * finished route would be an offer the session cannot honour.
 *
 * Nothing to undo, which is the point of putting the cancel here rather than in
 * a dialog before it: the learner gets to see what finishing would mean — the
 * recap, and what is still unresolved — and then decide, with the session
 * untouched behind them.
 */
export default function CompletionScreen({
  graph, onNewSession, onFinish, onResume,
}: {
  graph: SessionGraph;
  onNewSession: () => void;
  onFinish: () => void;
  /**
   * Go back to the stop the learner was on, exactly as it was.
   *
   * Absent when the journey genuinely ended. Present when they pressed
   * `Finish session early` or `Finish session`, which are the two clicks this
   * screen has to be cancellable from.
   */
  onResume?: () => void;
}) {
  const [tab, setTab] = useState<"summary" | "map">("summary");
  // "Another pass" must list what is STILL unresolved — not everything the
  // learner ever stumbled on. `weak_spot` is sticky, so it kept offering a
  // second pass over units already mastered.
  const weak = graph.nodes.filter((n) => n.understanding === "unresolved");
  const understood = graph.nodes.filter((n) => n.understanding_state === "understood").length;

  return (
    <div className="flex h-full flex-col gap-5">
      <div className="flex shrink-0 gap-1 border-b border-rule">
        {(["summary", "map"] as const).map((key) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-4 py-2 font-mono text-micro uppercase tracking-[0.12em] transition ${
              tab === key
                ? "border-signal text-signal"
                : "border-transparent text-graphite hover:text-chalk"
            }`}
          >
            {key === "map" ? t.completion.tabMap : t.completion.tabSummary}
          </button>
        ))}
      </div>

      {tab === "summary" ? (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col gap-2">
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
              {t.completion.label}
            </span>
            <h2 className="font-display text-chapter font-medium tracking-tight text-chalk">
              {t.completion.heading(understood, graph.nodes.length)}
            </h2>
            <p className="measure text-body text-paper">
              {t.completion.body}
            </p>
          </div>

          {weak.length > 0 && (
            <div className="flex flex-col gap-3 rounded-card border border-rule bg-slab p-4">
              <span className="font-mono text-micro uppercase tracking-[0.14em] text-rust">
                {t.completion.anotherPass(weak.length)}
              </span>
              <ul className="flex flex-col gap-2.5">
                {weak.map((n) => (
                  <li key={n.id} className="flex flex-col gap-0.5">
                    <span className="text-aside font-medium text-chalk">{n.title}</span>
                    <span className="font-mono text-micro text-graphite">
                      {n.file}
                      {" · "}
                      {t.lesson.lines(n.line_start, n.line_end)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* ORDER IS THE CONFIRMATION. Where the learner chose to stop, going
              back leads: nothing has been committed yet, and the two buttons
              beside it both leave the session. Where the walk ran out, the row is
              exactly what it always was. */}
          <div className="flex flex-wrap gap-3">
            {onResume && (
              <Button variant="primary" size="md" onClick={onResume}>
                {t.completion.keepGoing}
              </Button>
            )}
            <Button variant={onResume ? "secondary" : "primary"} size="md"
              onClick={onNewSession}
            >
              {t.completion.newSession}
            </Button>
            <Button variant={onResume ? "ghost" : "secondary"} size="md"
              onClick={onFinish}
            >
              {t.completion.goHome}
            </Button>
          </div>

          {onResume && (
            <p className="measure text-meta text-graphite">
              {t.completion.notFinishedYet}
            </p>
          )}
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-hidden rounded-card border border-rule">
          {/* The route only. The measures and the profile that used to come with
              this view live in Analysis now, and the recap above already states
              what was understood — so what is left here is the walk itself. */}
          <MapView
            nodes={graph.nodes}
            edges={graph.edges}
            areas={graph.areas}
            currentNodeId={graph.current_node_id}
            repoUrl={graph.repo_url}
            // A read-only recap: the stop card still describes a stop, and with
            // no handler it offers no way to walk to one. The live session is
            // where the route is navigable.
          />
        </div>
      )}
    </div>
  );
}
