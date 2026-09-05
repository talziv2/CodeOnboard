"use client";

import Button from "@/components/ui/Button";
import SectionLabel from "@/components/ui/SectionLabel";
import type { ScopeCheck } from "@/lib/api";
import { checkRows, type CheckRow } from "@/lib/contribution";
import { t } from "@/lib/strings";

/**
 * What CodeOnboard can honestly say about a change it did not run.
 *
 * THE THREE CLAIMS ARE KEPT APART HERE, and this is the surface where they would
 * collapse if anywhere did:
 *
 *   SCOPE        which files were touched      — our code decided it
 *   CORRECTNESS  does it do what was asked     — the Review step, labelled
 *   TESTS        does the repository pass      — NOBODY. Not run.
 *
 * So the scope row says *"no files outside the planned contribution boundary"*
 * and never *"correct"*, and it carries the caveat that the boundary was itself
 * derived during the investigation — a path comparison is a plan the learner
 * stayed inside, not evidence the change is right.
 *
 * THE EXECUTION ROW IS ALWAYS PRESENT AND NEVER CARRIES A TICK. A stage that
 * showed nothing about tests when none ran would be read as one that ran them.
 * `checkRows` puts it there unconditionally, with `tone: "none"`, for exactly
 * that reason.
 *
 * The symbol row is the one row that can be absent, and only because the change
 * boundary named no target symbol to compare against — an empty row would look
 * like a result while asserting nothing.
 */
const TONE_CLASS: Record<CheckRow["tone"], string> = {
  pass: "text-jade",
  fail: "text-rust",
  // Not a failure and not a pass — a statement about what did not happen.
  none: "text-graphite",
};

function rowText(row: CheckRow, check: ScopeCheck): string {
  switch (row.key) {
    case "scope":
      return row.tone === "pass"
        ? t.contribution.scopePassed
        : `${t.contribution.scopeFailed(row.detail.length)} — ${row.detail.join(", ")}`;
    case "syntax":
      return row.tone === "pass"
        ? t.contribution.syntaxPassed(check.in_boundary.length + check.outside_boundary.length)
        : `${t.contribution.syntaxFailed}: ${row.detail.join(", ")}`;
    case "symbol":
      return row.tone === "pass"
        ? t.contribution.symbolFound(check.symbol_expected)
        : t.contribution.symbolMissing(check.symbol_expected);
    case "protected":
      // Two sentences in one row, deliberately: what happened ("not performed")
      // and why it could not ("this check compares file paths, not symbols").
      // Without the second, "not performed" reads as an omission rather than a
      // limit, and someone will try to fix it by turning something on.
      return `${t.contribution.protectedNotPerformed} — ${
        t.contribution.protectedDetail(row.detail)
      }`;
    case "tests":
      return row.tone === "pass"
        ? `${t.contribution.testsFound} — ${row.detail.join(", ")}`
        : t.contribution.testsMissing;
    case "execution":
      return t.contribution.executionNever;
  }
}

export default function ValidateStep({
  check,
  command,
  onRun,
  onBack,
  onContinue,
  busy,
}: {
  check: ScopeCheck | null;
  command: string;
  onRun: () => void;
  onBack: () => void;
  onContinue: () => void;
  busy: boolean;
}) {
  const rows = checkRows(check);

  return (
    <section className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <SectionLabel tone="raised">{t.contribution.validateHeading}</SectionLabel>
        <p className="text-aside text-graphite">{t.contribution.validateNote}</p>
      </div>

      {!check ? (
        <div>
          <Button variant="primary" size="md" onClick={onRun} disabled={busy}>
            {busy ? t.contribution.validateRunning : t.contribution.validateRun}
          </Button>
        </div>
      ) : (
        <>
          <dl className="flex flex-col gap-2.5 rounded-panel border border-rule bg-well p-4">
            {rows.map((row) => (
              <div key={row.key} className="flex flex-col gap-0.5 sm:flex-row sm:gap-4">
                <dt className="font-mono text-micro uppercase tracking-[0.16em] text-graphite sm:w-40 sm:shrink-0">
                  {t.contribution.checks[row.key]}
                </dt>
                <dd className={`text-aside ${TONE_CLASS[row.tone]}`}>
                  {rowText(row, check)}
                </dd>
              </div>
            ))}
          </dl>

          {/* The caveat sits with the scope result, not in a footnote: the whole
              point is that it is read at the same moment as the word "passed". */}
          <p className="font-mono text-micro text-graphite">
            {check.in_boundary.length + check.outside_boundary.length + check.forbidden.length === 0
              ? t.contribution.scopeUndrawn
              : t.contribution.scopeCaveat}
          </p>

          {check.misnamed_tests.length > 0 && (
            <p className="text-aside text-brass">
              {t.contribution.testsMisnamed(check.misnamed_tests)}
            </p>
          )}

          <div className="flex flex-col gap-1.5 rounded-panel border border-rule bg-trench p-4">
            <SectionLabel>{t.contribution.commandLabel}</SectionLabel>
            {command ? (
              <>
                <code className="font-mono text-micro text-chalk">{command}</code>
                <p className="font-mono text-micro text-graphite">
                  {t.contribution.commandNote}
                </p>
              </>
            ) : (
              <p className="text-aside text-graphite">{t.contribution.commandNone}</p>
            )}
          </div>

          <div className="flex items-center gap-3">
            <Button variant="secondary" size="md" onClick={onBack}>
              {t.contribution.validateAgain}
            </Button>
            <Button variant="primary" size="md" onClick={onContinue}>
              {t.contribution.validateContinue}
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
