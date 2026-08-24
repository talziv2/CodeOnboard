"use client";

import type { Attempt } from "@/lib/api";
import SectionLabel from "@/components/ui/SectionLabel";
import Prose from "@/components/ui/Prose";
import { NEUTRAL, VERDICT_COLOR } from "@/lib/verdict";
import { t } from "@/lib/strings";

/**
 * Every graded answer on this stop, each collapsed to its verdict until opened.
 *
 * Moved out of `LessonPanel` unchanged. The list it is handed has already been
 * filtered and assembled by the panel, and that assembly is the part with the
 * sharp edges — verification answers are excluded because they carry no
 * classification, and a just-graded answer on the warm-up path is synthesised as
 * a `pending` attempt because the graph refresh is deliberately skipped there. So
 * this component takes attempts and renders them, and knows about neither rule.
 *
 * §3a asks whether this belongs on screen DURING feedback or only on demand. That
 * is an L4/L5 decision; extracting it changes nothing about when it appears.
 */
export default function AttemptHistory({ attempts }: { attempts: Attempt[] }) {
  return (
    <div className="flex flex-col gap-3">
      <SectionLabel>{t.lesson.yourAnswers(attempts.length)}</SectionLabel>
      <div className="flex flex-col gap-2">
        {attempts.map((attempt, i) => (
          <AttemptCard key={`${attempt.at}-${i}`} attempt={attempt} index={i} />
        ))}
      </div>
    </div>
  );
}

/** Chevron that points right when closed, down when open. */
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

function whenLabel(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.round((Date.now() - then) / 60000);
  if (mins < 1) return t.lesson.when.justNow;
  if (mins < 60) return t.lesson.when.minutes(mins);
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return t.lesson.when.hours(hrs);
  return new Date(iso).toLocaleDateString();
}

/** One graded answer, collapsed to its verdict until opened. */
function AttemptCard({ attempt, index }: { attempt: Attempt; index: number }) {
  /**
   * A CHECK has no verdict, and that is not an omission.
   *
   * It is graded per gap, and whether the stop is demonstrated is decided by
   * `understanding_of` from the latest ASSESSMENT plus the gap list — never by
   * this answer. So the row is labelled for what it is instead of borrowing a
   * verdict word it was never given.
   *
   * Checks were dropped from this list entirely until now, on the mechanical
   * grounds that a blank verdict rendered a blank row. The consequence, from a
   * real run: a learner cleared two gaps with a careful answer, returned to the
   * stop, and found the gaps marked resolved with no trace of what they wrote.
   * Labelling the row costs one string and keeps their words.
   */
  const isCheck = (attempt.kind ?? "assessment") === "verification";
  const closed = attempt.response?.gaps_resolved?.length ?? null;
  const label = isCheck
    ? t.lesson.checkRow
    : t.lesson.verdict[attempt.classification] ?? attempt.classification;
  const color = isCheck ? NEUTRAL : VERDICT_COLOR[attempt.classification] ?? NEUTRAL;

  return (
    <details className="group rounded-card border border-rule bg-slab open:bg-trench">
      <summary className="flex cursor-pointer list-none items-center gap-2.5 px-3 py-2">
        <span aria-hidden className="font-mono text-micro text-graphite">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span
          className="font-mono text-micro uppercase tracking-[0.13em]"
          style={{ color }}
        >
          {label}
        </span>
        {/* What the check achieved, where it is recorded. A row saying only
            "Check" leaves the learner to open it to find out whether it worked. */}
        {isCheck && closed !== null && (
          <span className="font-mono text-micro text-graphite">
            {closed > 0 ? t.lesson.checkRowCleared(closed) : t.lesson.checkRowClearedNone}
          </span>
        )}
        <span className="ms-auto font-mono text-micro text-graphite">
          {whenLabel(attempt.at)}
        </span>
        <Chevron />
      </summary>
      <div className="flex flex-col gap-2.5 border-t border-rule px-3 py-3">
        {/* WHAT WAS ASKED, above the answer to it (M1).
            Rendered only when the attempt actually carries it. Falling back to
            the node's current prompt would be worse than silence: after a
            re-teach that is a different question, so an old answer would be
            captioned with one the learner never saw. */}
        {attempt.question && (
          <div className="flex flex-col gap-1">
            <span className="flex flex-wrap items-baseline gap-x-2 font-mono text-micro uppercase tracking-[0.14em] text-graphite">
              {t.lesson.youWereAsked}
              {/* Only for the questions that are NOT the unit's original prompt.
                  That one is the unmarked case, and badging every row with
                  "lesson question" would be noise carrying no decision. */}
              {attempt.question_source &&
                t.lesson.askedBy[attempt.question_source] && (
                  <span className="rounded-chip bg-signal-wash px-1.5 py-px text-signal">
                    {t.lesson.askedBy[attempt.question_source]}
                  </span>
                )}
            </span>
            <Prose text={attempt.question} size="aside" tone="graphite" />
          </div>
        )}
        <div className="flex flex-col gap-1">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
            {t.lesson.youWrote}
          </span>
          <p className="measure whitespace-pre-wrap text-meta text-paper">
            {attempt.answer}
          </p>
        </div>
        {attempt.rationale && (
          <div className="flex flex-col gap-1">
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
              {t.lesson.feedback}
            </span>
            <p className="measure text-meta text-graphite">
              {attempt.rationale}
            </p>
          </div>
        )}
      </div>
    </details>
  );
}
