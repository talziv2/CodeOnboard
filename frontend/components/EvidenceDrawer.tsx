"use client";

import { useEffect, useState } from "react";
import type { EvidenceChain } from "@/lib/api";
import { getEvidence } from "@/lib/api";
import { understandingLabel, understandingStyle } from "@/lib/tags";
import Button from "@/components/ui/Button";
import { t } from "@/lib/strings";

/**
 * The evidence behind ONE unit's understanding state.
 *
 * The rule this component exists to keep: **every state the profile shows must
 * be explainable from persisted evidence.** So it renders the objective the
 * answer was marked against, the derived state, each attempt with its verdict,
 * and what the system did in response — and where there is no record, it says
 * so rather than defaulting.
 *
 * `intervention === null` means UNKNOWN, not "nothing happened". Every attempt
 * stored before the history milestone is in that state, and rendering them as
 * unassisted would invent a fact about 40 real answers.
 */
export default function EvidenceDrawer({
  sessionId, nodeId, onClose,
}: {
  sessionId: string;
  nodeId: string;
  onClose: () => void;
}) {
  const [chain, setChain] = useState<EvidenceChain | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    setChain(null);
    setFailed(false);
    getEvidence(sessionId, nodeId)
      .then((c) => live && setChain(c))
      .catch(() => live && setFailed(true));
    return () => { live = false; };
  }, [sessionId, nodeId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const style = chain ? understandingStyle(chain.understanding) : null;

  return (
    <aside
      role="dialog"
      aria-label={t.map.evidenceFor}
      className="flex h-full min-h-0 w-[26rem] shrink-0 flex-col gap-4 overflow-y-auto border-s border-rule bg-slab px-5 py-4"
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="font-mono text-micro uppercase tracking-[0.16em] text-graphite">
          {t.map.evidenceFor}
        </span>
        <Button variant="ghost"
          onClick={onClose}
        >
          {t.map.close}
        </Button>
      </div>

      {failed && <p className="text-meta text-rust">{t.session.loadFailed}</p>}
      {!chain && !failed && (
        <p className="animate-pulse font-mono text-micro text-graphite">
          {t.session.loading}
        </p>
      )}

      {chain && (
        <>
          <div className="flex flex-col gap-2">
            <h3 className="font-display text-lede font-medium text-chalk">
              {chain.title}
            </h3>
            <span className="flex items-center gap-2 font-mono text-micro">
              <span
                aria-hidden
                className="h-[calc(9rem/16)] w-[calc(9rem/16)] shrink-0 rounded-full border-[1.5px]"
                style={{ borderColor: style!.stroke, background: style!.fill,
                         borderStyle: style!.borderStyle }}
              />
              <span className="text-chalk">{understandingLabel(chain.understanding)}</span>
              {/* The second dimension, stated separately — never folded into
                  the first. */}
              {chain.disposition !== "active" && (
                <span className="text-graphite">
                  · {t.map.disposition[chain.disposition] ?? chain.disposition}
                </span>
              )}
            </span>
            {/* M7 can hold a unit back although the last answer reached the
                objective. M9 put gaps on the wire, so the drawer now says WHY
                rather than only THAT — the reason is named below. */}
            {/* WHY this unit is not demonstrated, in one sentence, from M9's
                counters (AC12). The drawer already lists the gap claims below;
                what was missing was the summary line that explains the STATE —
                "still open" and "you chose not to pursue this" produce the same
                classification for completely different reasons. */}
            {chain.understanding === "unresolved" && (
              <p className="text-meta text-brass">
                {chain.verification_pending
                  ? t.map.whyPendingVerification
                  : (chain.gaps_waived ?? 0) > 0 && (chain.gaps_open ?? 0) === 0
                    ? t.map.whyWaived(chain.gaps_waived!)
                    : (chain.gaps_open ?? 0) > 0
                      ? t.map.whyOpenGaps(chain.gaps_open!)
                      : t.map.whyNotYetDemonstrated}
              </p>
            )}
            {chain.understanding !== "unresolved"
              && !chain.state_matches_latest_answer && (
              <p className="text-meta text-brass">
                {t.map.pendingVerification}
              </p>
            )}
            {(chain.gaps?.length ?? 0) > 0 && (
              <div className="flex flex-col gap-1.5 border-t border-rule pt-2">
                <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
                  {t.map.gapsLabel}
                </span>
                {chain.gaps!.map((gap) => (
                  <div key={gap.id} className="flex flex-col">
                    <span className="text-meta text-paper">
                      {gap.claim}
                    </span>
                    <span className="font-mono text-micro uppercase tracking-[0.12em] text-graphite">
                      {/* Every status is shown, not only the open ones: "this
                          was waived" explains a state as much as "this is still
                          open" does. */}
                      {gap.status === "verified"
                        ? t.map.gapVerified
                        : gap.status === "waived"
                          ? t.map.gapWaived
                          : gap.exhausted
                            ? t.map.gapExhausted
                            : gap.blocking
                              ? t.map.gapBlocking
                              : t.map.gapNonBlocking}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {chain.objective && (
            <div className="flex flex-col gap-1 border-t border-rule pt-3">
              <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
                {t.map.objectiveLabel}
              </span>
              <p className="text-meta text-paper">
                {chain.objective}
              </p>
            </div>
          )}

          <div className="flex flex-col gap-3 border-t border-rule pt-3">
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
              {t.map.timeline}
            </span>

            {chain.timeline.length === 0 && (
              <p className="text-meta text-graphite">{t.map.noEvidenceYet}</p>
            )}

            <ol className="flex flex-col gap-3.5">
              {chain.timeline.map((step) => (
                <li key={step.index} className="flex flex-col gap-1.5">
                  <span className="flex flex-wrap items-baseline gap-2 font-mono text-micro">
                    <span className="text-graphite">
                      {t.map.yourAnswer} {step.index + 1}
                    </span>
                    <span className="text-chalk">
                      {t.lesson.verdict[step.classification] ?? step.classification}
                    </span>
                    {!step.graded && (
                      <span className="text-brass">· {t.map.gradingFailed}</span>
                    )}
                    {step.graded && !step.counts_as_evidence && (
                      <span className="text-graphite">· {t.map.notEvidence}</span>
                    )}
                  </span>

                  {/* WHAT WAS ASKED (M1). The drawer's whole job is to make a
                      state traceable, and up to three different questions can
                      produce an answer on one node — the unit's prompt, one a
                      re-teach installed, and a gap check. Without this the chain
                      it draws skips a link. `null` where unrecorded; never
                      substituted from the node's current prompt. */}
                  {step.question && (
                    <p className="text-meta italic text-graphite">
                      {step.question_source &&
                        t.lesson.askedBy[step.question_source] && (
                          <span className="me-1.5 font-mono text-micro uppercase not-italic tracking-[0.13em] text-signal">
                            {t.lesson.askedBy[step.question_source]}
                          </span>
                        )}
                      {step.question}
                    </p>
                  )}

                  <p className="border-s-2 border-rule ps-2.5 text-meta text-paper">
                    {step.answer}
                  </p>

                  {step.rationale && (
                    <p className="text-meta text-graphite">
                      {step.rationale}
                    </p>
                  )}

                  {/* null = no record. Rendering it as "nothing happened" would
                      invent history for every pre-instrumentation answer. */}
                  <span className="font-mono text-micro text-graphite">
                    {t.map.systemDid}:{" "}
                    {step.intervention === null ? (
                      <span className="italic">{t.map.noRecord}</span>
                    ) : (
                      <span className="text-signal">
                        {t.map.interventionLabel[step.intervention] ?? step.intervention}
                      </span>
                    )}
                  </span>

                  {step.intervention_text && (
                    <p className="rounded-field border border-rule bg-raise px-2.5 py-1.5 text-meta text-paper">
                      {step.intervention_text}
                    </p>
                  )}

                  {step.superseded_lesson && (
                    <span className="font-mono text-micro text-graphite">
                      {t.map.supersededLesson}
                    </span>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </>
      )}
    </aside>
  );
}
