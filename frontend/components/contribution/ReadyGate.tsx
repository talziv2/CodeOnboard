"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import Callout from "@/components/ui/Callout";
import SectionLabel from "@/components/ui/SectionLabel";
import type { Contribution } from "@/lib/api";
import { t } from "@/lib/strings";

/**
 * The door into the implementation stage, and the two ways through it.
 *
 * THE GATE IS THE PRODUCT CLAIM. `contribution.ready.ready` is server-owned —
 * every required unit demonstrated, no open blocking gap on one — and this
 * component renders it rather than deciding it. Blocking required knowledge
 * genuinely stops implementation; that is the thing the whole journey exists to
 * demonstrate, so there is no client-side path around it.
 *
 * THE OVERRIDE IS NOT AN EQUAL SECOND OPTION. It is a quiet link, it is
 * confirmation-gated, and `overrideAvailable` in `lib/contribution.ts` decides
 * whether it appears at all — only after the learner has actually worked a
 * blocking stop and it has not resolved. Somebody who has answered nothing is
 * not stuck; they have not started, and offering them a way past the learning
 * would undercut the one claim the demo is making.
 *
 * What it buys is that `/plan` stops refusing. It writes no understanding, moves
 * no readiness number, and closes no gap: the blockers below stay on screen
 * afterwards, and the completion screen still says the change was implemented
 * with concepts unverified.
 */
export default function ReadyGate({
  contribution,
  overrideOffered,
  onStart,
  onProceedUnready,
  busy,
}: {
  contribution: Contribution;
  /** Decided by `overrideAvailable` — never by this component. */
  overrideOffered: boolean;
  onStart: () => void;
  onProceedUnready: () => void;
  busy: boolean;
}) {
  const [confirming, setConfirming] = useState(false);
  const { ready } = contribution;

  if (ready.ready || contribution.state?.proceeded_unready) {
    return (
      <section className="flex flex-col gap-5 rounded-panel border border-rule bg-well p-6">
        <SectionLabel tone="raised">{t.contribution.readyLabel}</SectionLabel>
        <h2 className="text-title text-chalk">{t.contribution.readyHeading}</h2>
        {ready.ready ? (
          <p className="text-body text-paper">
            {t.contribution.readyBody(ready.required)}
          </p>
        ) : (
          // The honest version for a learner who chose to go on. It says what
          // happened rather than congratulating them on readiness they do not
          // have — the override never becomes a claim about understanding.
          <Callout tone="brass" label={t.contribution.overrideNotice}>
            <ul className="flex flex-col gap-1">
              {ready.blockers.map((b) => (
                <li key={b.node_id} className="text-aside text-paper">
                  {b.title}
                </li>
              ))}
            </ul>
          </Callout>
        )}
        <div>
          <Button variant="primary" size="lg" onClick={onStart} disabled={busy}>
            {busy ? t.contribution.planWriting : t.contribution.readyBegin}
          </Button>
        </div>
      </section>
    );
  }

  if (confirming) {
    return (
      <section className="flex flex-col gap-4 rounded-panel border border-rule bg-well p-6">
        <SectionLabel tone="raised">{t.contribution.overrideHeading}</SectionLabel>
        <p className="text-body text-paper">{t.contribution.overrideBody}</p>
        <ul className="flex flex-col gap-1.5">
          {ready.blockers.map((b) => (
            <li key={b.node_id} className="text-aside text-paper">
              <span className="text-chalk">{b.title}</span>
              {b.gaps.length > 0 && (
                <span className="text-graphite"> — {b.gaps[0].claim}</span>
              )}
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-3">
          <Button variant="secondary" size="md" onClick={() => setConfirming(false)}>
            {t.contribution.overrideCancel}
          </Button>
          <Button
            variant="ghost"
            onClick={onProceedUnready}
            disabled={busy}
            className="text-graphite underline underline-offset-4"
          >
            {t.contribution.overrideConfirm}
          </Button>
        </div>
      </section>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-aside text-graphite">
        {t.contribution.gateProgress(ready.demonstrated, ready.required)}
      </p>
      {ready.blockers.slice(0, 1).map((b) => (
        <p key={b.node_id} className="text-aside text-paper">
          {t.contribution.gateBlocked(b.title)}
        </p>
      ))}
      {overrideOffered && (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="self-start font-mono text-micro text-graphite underline underline-offset-4 hover:text-paper"
        >
          {t.contribution.overrideLink}
        </button>
      )}
    </div>
  );
}
