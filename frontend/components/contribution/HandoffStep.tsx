"use client";

import { useEffect, useState } from "react";
import Button from "@/components/ui/Button";
import Callout from "@/components/ui/Callout";
import SectionLabel from "@/components/ui/SectionLabel";
import Disclosure from "@/components/ui/Disclosure";
import { getHandoff, type Handoff } from "@/lib/api";
import { errorText } from "@/lib/strings";
import { t } from "@/lib/strings";

/**
 * WHERE THE JOURNEY ENDS AND THE WORK BEGINS.
 *
 * CodeOnboard cannot execute, cannot edit a working tree and cannot open a pull
 * request — `data/repos/<owner>/<name>` is one shared, pinned checkout that the
 * grounding oracle reads, so a writable per-learner tree is a thing this system
 * must not have where it keeps the repository. Everything past "write the
 * change" was being simulated; this hands it to a tool that genuinely has those
 * capabilities, along with everything CodeOnboard learned.
 *
 * THE TWO HALVES ARE DRAWN APART ON PURPOSE. "About the code" and "About you"
 * are separate blocks with separate headings, because a reader who merges them
 * is making the claim D8 exists to prevent — that demonstrating eleven concepts
 * is a fact about the patch, or that a boundary is a fact about the learner.
 *
 * This renders; it does not derive (D22). The payload is
 * `GET /contribution/handoff`, which is the SAME `handoff.build_context` the MCP
 * tool returns — so what is on screen and what the agent receives cannot
 * disagree.
 */
export default function HandoffStep({
  sessionId,
  onFallback,
}: {
  sessionId: string;
  /** The old in-app steps, kept reachable until this flow is verified. */
  onFallback: () => void;
}) {
  const [handoff, setHandoff] = useState<Handoff | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let live = true;
    getHandoff(sessionId).then(
      (h) => live && setHandoff(h),
      (e: unknown) => live && setError(
        e instanceof Error ? errorText(e.message) : t.contribution.handoffUnavailable,
      ),
    );
    return () => { live = false; };
  }, [sessionId]);

  if (error) {
    return (
      <section className="flex flex-col gap-4">
        <SectionLabel tone="raised">{t.contribution.handoffLabel}</SectionLabel>
        <Callout tone="brass" label={t.contribution.handoffLabel}>
          <p className="text-aside text-paper">{error}</p>
        </Callout>
        <div>
          <Button variant="secondary" size="md" onClick={onFallback}>
            {t.contribution.handoffFallback}
          </Button>
        </div>
      </section>
    );
  }
  if (!handoff) {
    return (
      <p className="animate-pulse font-mono text-aside text-graphite">
        {t.session.loading}
      </p>
    );
  }

  const { context: c } = handoff;
  const config = JSON.stringify(handoff.setup.mcp_json, null, 2);
  const boundary = c.change_boundary;

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <SectionLabel tone="raised">{t.contribution.handoffLabel}</SectionLabel>
        <h2 className="text-title text-chalk">{t.contribution.handoffHeading}</h2>
        <p className="text-aside text-graphite">{t.contribution.handoffBody}</p>
      </div>

      {/* ── THE ACTION, FIRST ─────────────────────────────────────────────
          ABOVE the summary, not below it. What travels is long — eleven
          objectives and five boundary sections — and a learner who has already
          decided to go and implement should not have to scroll past everything
          CodeOnboard knows to reach the one control that takes them there. The
          summary is worth reading; it is not a precondition for leaving.

          ONE CONTROL, and a link rather than a button because it opens another
          application: `claude-cli://open?cwd=<absolute path>`.

          AN ABSOLUTE PATH, NOT A REPOSITORY SLUG. `repo=<owner>/<name>` was
          tried first and is not reliable — Claude Code resolves a slug only
          against clones it has already opened, and when it cannot it does not
          fail, it opens somewhere else. Measured: no clone existed, the link
          opened the home directory, and the MCP server was simply absent. The
          path is derived server-side from the project root and this session's
          repository URL (`workspace/<owner>/<name>`), so nothing machine-
          specific is written down, and `null` means no button at all.

          The context does NOT travel in this link. It travels through
          `get_contribution_context`, which is the whole reason the MCP server
          exists — and is why the link stays far below the ~5000 character cap. */}
      <div className="flex flex-col gap-2">
        {handoff.setup.deep_link ? (
          <>
            <a
              href={handoff.setup.deep_link}
              className="inline-flex w-fit items-center gap-2 rounded-field bg-signal px-4 py-2 font-medium text-ink transition hover:bg-chalk"
            >
              {t.contribution.handoffOpen}
            </a>
            <p className="text-micro text-graphite">{t.contribution.handoffOpenHint}</p>
            {/* WHERE it opens, on screen. The destination is a configured
                absolute path, and a launch control whose target is invisible is
                one you cannot tell has gone to the wrong place. */}
            {handoff.setup.workspace && (
              <p className="font-mono text-micro text-graphite">
                {t.contribution.handoffOpenIn(handoff.setup.workspace)}
              </p>
            )}
            <p className="text-micro text-graphite">{t.contribution.handoffAfter}</p>
          </>
        ) : (
          <Callout tone="brass" label={t.contribution.handoffOpen}>
            <p className="text-aside text-paper">{t.contribution.handoffNoWorkspace}</p>
          </Callout>
        )}
        <p className="text-micro text-graphite">{t.contribution.handoffAgentRole}</p>
      </div>


      <div className="flex flex-col gap-5 rounded-panel border border-rule bg-well p-4">
        <SectionLabel>{t.contribution.handoffWhatTravels}</SectionLabel>

        <Field label={t.contribution.handoffTask}>
          <p className="whitespace-pre-wrap text-aside text-paper">{c.task}</p>
        </Field>

        {/* The revision is not a courtesy field: every file and symbol below is
            true at ONE commit, and read against a different checkout the whole
            thing is confidently wrong — worse than empty. */}
        <Field label={t.contribution.handoffRevision}>
          <p className="font-mono text-micro text-chalk">
            {c.repository.commit.slice(0, 12)}
          </p>
          <p className="text-micro text-graphite">
            {t.contribution.handoffRevisionHint}
          </p>
        </Field>

        {/* ── about the code ─────────────────────────────────────────────── */}
        <div className="flex flex-col gap-3 border-t border-rule pt-4">
          <SectionLabel tone="raised">{t.contribution.handoffCodeHalf}</SectionLabel>
          <Anchors label={t.contribution.handoffTargets} rows={boundary.target} />
          <Anchors
            label={t.contribution.handoffProtected}
            rows={boundary.must_not_change}
          />
          <Anchors
            label={t.contribution.handoffTests}
            rows={boundary.existing_tests}
          />
          <Lines
            label={t.contribution.handoffEdgeCases}
            items={(boundary.edge_cases ?? []).map((e) => e.case ?? "")}
          />
          <Lines
            label={t.contribution.handoffContracts}
            items={c.contracts.map((x) => x.contract)}
          />
          {c.recommended_validation && (
            <Field label={t.contribution.handoffValidation}>
              <p className="font-mono text-micro text-chalk">
                {c.recommended_validation}
              </p>
              {/* Never "passing". Nothing on either side of this has run it. */}
              <p className="text-micro text-graphite">
                {t.contribution.handoffValidationHint}
              </p>
            </Field>
          )}
        </div>

        {/* ── about the learner ──────────────────────────────────────────── */}
        <div className="flex flex-col gap-3 border-t border-rule pt-4">
          <SectionLabel tone="raised">{t.contribution.handoffLearnerHalf}</SectionLabel>
          <p className="text-aside text-paper">
            {t.contribution.handoffDemonstrated(c.learner.demonstrated)}
          </p>
          <Lines label="" items={c.learner.demonstrated_concepts} />
          {c.learner.not_taught.length > 0 && (
            <Lines
              label={t.contribution.handoffNotTaught}
              items={c.learner.not_taught.map((a) => a.name)}
            />
          )}
          {/* The sentence travels WITH the number, here and in the payload:
              without it "11 demonstrated" reads as a certification. */}
          <Field label={t.contribution.handoffMeansLabel}>
            <p className="text-micro text-graphite">{c.learner.means}</p>
          </Field>
        </div>
      </div>

      {/* Everything mechanical, folded away. A learner does not need it; the
          person reproducing this on another machine does. */}
      <Disclosure label={t.contribution.handoffSetupLabel}>
        <div className="flex flex-col gap-3">
          <p className="text-aside text-graphite">{t.contribution.handoffSetupNote}</p>
          <p className="text-aside text-graphite">{t.contribution.handoffClone}</p>
          <ol className="flex flex-col gap-1.5">
            {[t.contribution.handoffStep1, t.contribution.handoffStep2,
              t.contribution.handoffStep3].map((step, i) => (
              <li key={i} className="flex gap-2.5 text-aside text-paper">
                <span className="font-mono text-micro text-graphite">{i + 1}.</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
          <pre className="max-h-56 overflow-auto rounded-field border border-rule bg-trench p-3 font-mono text-micro text-paper">
            {config}
          </pre>
          <div className="flex items-center gap-3">
            <Button
              variant="secondary"
              size="md"
              onClick={() => {
                // Absent in insecure contexts and in some test environments. A
                // copy button that throws is worse than one that quietly does
                // nothing — the config is on screen either way.
                navigator.clipboard?.writeText(config).then(
                  () => setCopied(true), () => {},
                );
              }}
            >
              {copied ? t.contribution.handoffCopied : t.contribution.handoffCopyConfig}
            </Button>
          </div>
        </div>
      </Disclosure>

      <div>
        <button
          type="button"
          onClick={onFallback}
          className="self-start font-mono text-micro text-graphite underline underline-offset-4 hover:text-paper"
        >
          {t.contribution.handoffFallback}
        </button>
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <SectionLabel>{label}</SectionLabel>
      {children}
    </div>
  );
}

function Anchors({
  label, rows,
}: { label: string; rows?: { file?: string; symbol?: string }[] }) {
  if (!rows || rows.length === 0) return null;
  return (
    <Field label={label}>
      <ul className="flex flex-col gap-0.5">
        {rows.map((row, i) => (
          <li key={i} className="font-mono text-micro text-chalk">
            {row.file}{row.symbol ? `:${row.symbol}` : ""}
          </li>
        ))}
      </ul>
    </Field>
  );
}

function Lines({ label, items }: { label: string; items: string[] }) {
  const rows = items.filter(Boolean);
  if (rows.length === 0) return null;
  return (
    <Field label={label}>
      <ul className="flex flex-col gap-1">
        {rows.map((item, i) => (
          <li key={i} className="flex gap-2.5 text-aside text-paper">
            <span aria-hidden className="text-graphite">·</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </Field>
  );
}
