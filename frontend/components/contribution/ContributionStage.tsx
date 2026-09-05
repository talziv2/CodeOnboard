"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import Callout from "@/components/ui/Callout";
import SectionLabel from "@/components/ui/SectionLabel";
import Prose from "@/components/ui/Prose";
import ImplementStep from "@/components/contribution/ImplementStep";
import ValidateStep from "@/components/contribution/ValidateStep";
import HandoffStep from "@/components/contribution/HandoffStep";
import type { Contribution, ContributionStage as Stage, PatchFile } from "@/lib/api";
import {
  forbiddenRows, isFallbackStep, suggestedPaths, targetRows, testRows,
  type StepView,
} from "@/lib/contribution";
import { t } from "@/lib/strings";

/**
 * Plan → Locate → Implement → Validate → Review, and then the PR-ready result.
 *
 * THESE ARE NOT LEARNING-GRAPH NODES, and the whole design turns on that. Five
 * stages in the walk would move `journey_progress` and `stops_total`, and any of
 * them marked required would enter `goal_readiness`'s denominator — the defect
 * `backend/learning/progress.py`'s header records, where the gauge fell the
 * moment the system decided to help (D7). They carry no objective, nothing here
 * is graded, and writing a patch is a learner action that must never move
 * `understanding_state` (D8). So this is a phase of the session page, rendered
 * where `CompletionScreen` renders, with the route rail still beside it.
 *
 * The stage lives on the server. Every action posts and gets the whole
 * `Contribution` payload back, so the stage and the state it produced arrive
 * together — a POST followed by a refetch could show a stage whose own result
 * had not landed yet.
 */
export default function ContributionStage({
  contribution,
  onPlan,
  onSavePatch,
  onValidate,
  onReview,
  onPr,
  onOpenFile,
  onStuck,
  onBack,
  busy,
  viewing,
  onView,
  sessionId,
}: {
  contribution: Contribution;
  onPlan: () => void;
  onSavePatch: (files: PatchFile[]) => void;
  onValidate: () => void;
  onReview: () => void;
  onPr: () => void;
  onOpenFile: (path: string) => void;
  onStuck?: () => void;
  onBack: () => void;
  busy: boolean;
  /**
   * Which stage the learner is LOOKING at — `null` follows the server's own.
   *
   * It lets them step back through stages they have passed without the server's
   * stage moving backwards: the server's stage is the furthest they reached,
   * this is where they are.
   *
   * OWNED BY THE PAGE, not by this component, because the route rail draws the
   * same five stages and has to highlight the same one. It was local state here
   * until the rail gained that section; two copies of "which stage is on screen"
   * is precisely the seam `frontend/CLAUDE.md` names — the rail would have gone
   * on pointing at the server's stage while the stepper showed another.
   */
  viewing: StepView | null;
  onView: (stage: StepView | null) => void;
  /** The session id — the handoff reads its own payload. */
  sessionId: string;
}) {
  const state = contribution.state;
  const stage: StepView = viewing ?? state?.stage ?? "plan";
  // The old in-app steps are reachable only through the handoff's own link now,
  // and they announce themselves as the fallback rather than borrowing the
  // three-step flow's stepper — which would mark "Continue in Claude Code"
  // current while showing the patch editor.
  const fallback = isFallbackStep(stage);
  /**
   * How far the stepper lets the learner click.
   *
   * `Math.max` with the stage being VIEWED, not the server's stage alone, and
   * that is not cosmetic: `POST /patch` advances the server to `implement`, and
   * the server only reaches `validate` when `/validate` is called — which the UI
   * offers from the Validate step. Gating on the server's stage alone therefore
   * dead-ends a learner who has just saved their change: Validate is the next
   * thing to do and the only control that could reach it is disabled.
   */
  return (
    <div className="flex flex-col gap-6">
      {/* THE STEPPER IS NOT HERE ANY MORE. Plan / Locate / Continue in Claude
          live in `ImplementationBar`, the column's own chrome, where the learning
          phase's tabs would otherwise be — so the phase has one navigation rather
          than a header that belongs to the other phase and a stepper inside the
          panel. What stays is the thing the panel is about. */}
      <p className="whitespace-pre-wrap text-aside text-paper">{contribution.task}</p>

      {contribution.state?.proceeded_unready && (
        <Callout tone="brass" label={t.contribution.overrideNotice}>
          <p className="text-aside text-paper">
            {t.contribution.gateProgress(
              contribution.ready.demonstrated, contribution.ready.required,
            )}
          </p>
        </Callout>
      )}

      {stage === "plan" && (
        <section className="flex flex-col gap-4">
          <SectionLabel tone="raised">{t.contribution.planHeading}</SectionLabel>
          <p className="text-aside text-graphite">{t.contribution.planNote}</p>
          {state?.plan ? (
            <>
              <ol className="flex flex-col gap-4">
                {state.plan.steps.map((step, i) => (
                  <li key={i} className="flex flex-col gap-1">
                    <span className="text-body text-chalk">
                      {i + 1}. {step.title}
                    </span>
                    <Prose text={step.detail} size="aside" tone="paper" />
                  </li>
                ))}
              </ol>
              <div className="flex items-center gap-3">
                <Button variant="secondary" size="md" onClick={onPlan} disabled={busy}>
                  {t.contribution.planRegenerate}
                </Button>
                <Button variant="primary" size="md" onClick={() => onView("locate")}>
                  {t.contribution.planContinue}
                </Button>
              </div>
            </>
          ) : (
            <Button variant="primary" size="md" onClick={onPlan} disabled={busy}>
              {busy ? t.contribution.planWriting : t.contribution.planHeading}
            </Button>
          )}
        </section>
      )}

      {stage === "locate" && (
        <section className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <SectionLabel tone="raised">{t.contribution.locateHeading}</SectionLabel>
            <p className="text-aside text-graphite">{t.contribution.locateNote}</p>
          </div>
          {targetRows(contribution.boundary).length === 0
            && forbiddenRows(contribution.boundary).length === 0 ? (
            <p className="text-aside text-graphite">{t.contribution.locateEmpty}</p>
          ) : (
            <>
              <BoundaryList
                label={t.contribution.locateTargets}
                rows={targetRows(contribution.boundary)}
                onOpen={onOpenFile}
              />
              <BoundaryList
                label={t.contribution.locateForbidden}
                rows={forbiddenRows(contribution.boundary)}
                onOpen={onOpenFile}
              />
              <BoundaryList
                label={t.contribution.locateTests}
                rows={testRows(contribution.boundary)}
                onOpen={onOpenFile}
              />
            </>
          )}
          <div>
            <Button variant="primary" size="md" onClick={() => onView("handoff")}>
              {t.contribution.handoffLabel}
            </Button>
          </div>
        </section>
      )}

      {stage === "handoff" && (
        <HandoffStep sessionId={sessionId} onFallback={() => onView("implement")} />
      )}

      {fallback && (
        <div className="flex items-center gap-3">
          <SectionLabel tone="raised">{t.contribution.handoffFallbackLabel}</SectionLabel>
          <button
            type="button"
            onClick={() => onView("handoff")}
            className="font-mono text-micro text-graphite underline underline-offset-4 hover:text-paper"
          >
            {t.contribution.handoffBackFromFallback}
          </button>
        </div>
      )}

      {stage === "implement" && (
        <ImplementStep
          patch={state?.patch ?? []}
          suggestions={suggestedPaths(contribution.boundary)}
          // Straight on to the check — the button says "Save and check", and
          // the check is the next thing the learner is being offered.
          onSave={(files) => { onView("validate"); onSavePatch(files); }}
          onStuck={onStuck}
          busy={busy}
        />
      )}

      {stage === "validate" && (
        <ValidateStep
          check={state?.scope_check ?? null}
          command={contribution.validation_command}
          onRun={() => { onView(null); onValidate(); }}
          onBack={() => onView("implement")}
          onContinue={() => onView("review")}
          busy={busy}
        />
      )}

      {stage === "review" && (
        <section className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <SectionLabel tone="raised">{t.contribution.reviewHeading}</SectionLabel>
            {/* The label is what keeps this from being read as the scope check's
                sibling: one is a fact our code decided, this is an opinion. */}
            <p className="text-aside text-graphite">{t.contribution.reviewNote}</p>
          </div>
          {state?.review ? (
            <>
              <p className="text-body text-chalk">
                {state.review.meets_task
                  ? t.contribution.reviewMeets
                  : t.contribution.reviewMisses}
              </p>
              <Bullets
                label={t.contribution.reviewObservations}
                items={state.review.observations}
              />
              <Bullets
                label={t.contribution.reviewConcerns}
                items={state.review.concerns}
                empty={t.contribution.reviewNoConcerns}
              />
              <div className="flex items-center gap-3">
                <Button variant="secondary" size="md" onClick={() => onView("implement")}>
                  {t.contribution.validateAgain}
                </Button>
                <Button variant="primary" size="md" onClick={() => { onView(null); onPr(); }} disabled={busy}>
                  {busy ? t.contribution.prWriting : t.contribution.reviewContinue}
                </Button>
              </div>
            </>
          ) : (
            <Button variant="primary" size="md" onClick={() => { onView(null); onReview(); }} disabled={busy}>
              {busy ? t.contribution.reviewRunning : t.contribution.reviewRun}
            </Button>
          )}
        </section>
      )}

      {stage === "done" && state && (
        <section className="flex flex-col gap-5">
          <SectionLabel tone="raised">{t.contribution.doneLabel}</SectionLabel>
          <h2 className="text-title text-chalk">{t.contribution.doneHeading}</h2>

          <dl className="flex flex-col gap-2 rounded-panel border border-rule bg-well p-4">
            <Row label={t.contribution.doneFiles}>
              {state.patch.map((f) => f.path).join(", ") || "—"}
            </Row>
            <Row label={t.contribution.doneScope}>
              {state.scope_check?.passed
                ? t.contribution.scopePassed
                : t.contribution.scopeFailed(
                    (state.scope_check?.outside_boundary.length ?? 0)
                      + (state.scope_check?.forbidden.length ?? 0),
                  )}
            </Row>
            {/* Always shown, never a tick. The result is that nothing ran. */}
            <Row label={t.contribution.doneTests}>{t.contribution.executionNever}</Row>
          </dl>

          {state.pr && (
            <div className="flex flex-col gap-4 rounded-panel border border-rule bg-well p-4">
              <SectionLabel>{t.contribution.prHeading}</SectionLabel>
              <Copyable label={t.contribution.prTitle} text={state.pr.title} />
              <Copyable label={t.contribution.prBody} text={state.pr.body} />
              <Copyable label={t.contribution.prTesting} text={state.pr.testing_notes} />
            </div>
          )}

          <div>
            <Button variant="secondary" size="md" onClick={onBack}>
              {t.contribution.backToJourney}
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:gap-4">
      <dt className="font-mono text-micro uppercase tracking-[0.16em] text-graphite sm:w-32 sm:shrink-0">
        {label}
      </dt>
      <dd className="text-aside text-paper">{children}</dd>
    </div>
  );
}

function Bullets({
  label, items, empty,
}: { label: string; items: string[]; empty?: string }) {
  if (items.length === 0 && !empty) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <SectionLabel>{label}</SectionLabel>
      {items.length === 0 ? (
        <p className="text-aside text-graphite">{empty}</p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {items.map((item, i) => (
            <li key={i} className="flex gap-2.5 text-aside text-paper">
              <span aria-hidden className="text-graphite">·</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function BoundaryList({
  label, rows, onOpen,
}: {
  label: string;
  rows: { file: string; symbol: string; reason: string }[];
  onOpen: (path: string) => void;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <SectionLabel>{label}</SectionLabel>
      <ul className="flex flex-col gap-2">
        {rows.map((row, i) => (
          <li key={`${row.file}:${row.symbol}:${i}`} className="flex flex-col gap-0.5">
            <button
              type="button"
              onClick={() => onOpen(row.file)}
              className="self-start text-start font-mono text-micro text-chalk underline underline-offset-4 hover:text-signal"
            >
              {row.file}
              {row.symbol ? `:${row.symbol}` : ""}
            </button>
            <span className="text-aside text-graphite">{row.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Copyable({ label, text }: { label: string; text: string }) {
  const [copied, setCopied] = useState(false);
  if (!text) return null;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-3">
        <SectionLabel>{label}</SectionLabel>
        <button
          type="button"
          onClick={() => {
            // `navigator.clipboard` is absent in insecure contexts and in some
            // test environments; a copy button that throws is worse than one
            // that quietly does nothing, and the text is on screen either way.
            navigator.clipboard?.writeText(text).then(
              () => setCopied(true),
              () => {},
            );
          }}
          className="font-mono text-micro text-graphite hover:text-paper"
        >
          {copied ? t.contribution.copied : t.contribution.copy}
        </button>
      </div>
      <p className="whitespace-pre-wrap rounded-field border border-rule bg-trench p-3 text-aside text-paper">
        {text}
      </p>
    </div>
  );
}
