"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import GoalDialogue from "@/components/GoalDialogue";
import SettingsMenu from "@/components/SettingsMenu";
import StartingProgress from "@/components/StartingProgress";
import { checkRepo, sessionStart } from "@/lib/api";
import Button from "@/components/ui/Button";
import { errorText, t } from "@/lib/strings";

type Step = "repo" | "goal" | "starting" | "failed";

const RECENT_KEY = "codeonboard:recent-repos";

function readRecent(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    return raw ? (JSON.parse(raw) as string[]).slice(0, 4) : [];
  } catch {
    return [];
  }
}

function rememberRepo(url: string) {
  try {
    const next = [url, ...readRecent().filter((r) => r !== url)].slice(0, 4);
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable — recents are a convenience, not a requirement */
  }
}

export default function Home() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("repo");
  const [repoUrl, setRepoUrl] = useState("");
  // Arriving from the briefing's "change your answers" (P4): the repository is
  // already known, so it is carried in the URL and the learner starts at the
  // question they wanted to change rather than at the address bar.
  //
  // Prefill only. It does NOT auto-submit: a learner who followed that link may
  // have wanted a different repository too, and skipping the step they are looking
  // at would take the decision away from them.
  useEffect(() => {
    const carried = new URLSearchParams(window.location.search).get("repo");
    if (carried) setRepoUrl(carried);
  }, []);
  const [recent, setRecent] = useState<string[]>([]);
  // Invented per run and sent with /session/start, so the progress screen can
  // poll what that call is doing while it blocks.
  const [startedGoal, setStartedGoal] = useState<Record<string, string> | null>(null);
  const [progressId, setProgressId] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Kept so a failed pipeline can be retried without redoing the interview.
  const [goal, setGoal] = useState<Record<string, string> | null>(null);

  useEffect(() => setRecent(readRecent()), []);

  // Verify the repo can actually be cloned before spending five questions on it.
  const handleRepoSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim() || checking) return;
    setError(null);
    setChecking(true);
    try {
      const { ok, reason } = await checkRepo(repoUrl.trim());
      if (!ok) {
        setError(reason ? errorText(reason) : t.home.repoUnreachable);
        return;
      }
      setStep("goal");
    } catch (err: unknown) {
      setError(err instanceof Error ? errorText(err.message) : t.home.serverUnreachable);
    } finally {
      setChecking(false);
    }
  };

  const startSession = async (forGoal: Record<string, string>) => {
    const runId = crypto.randomUUID();
    setProgressId(runId);
    // Kept so the generation screen can show what the wait is for (P3). The
    // interview unmounts the moment the step changes, so without this the goal
    // exists only inside the request that is in flight.
    setStartedGoal(forGoal);
    setStep("starting");
    setError(null);
    try {
      const { session_id } = await sessionStart(repoUrl, forGoal, false, runId);
      rememberRepo(repoUrl);
      // Land on the welcome page, not the first lesson: after a wait this long,
      // the first thing owed is what the repository is and what the system took
      // the goal to be — both checkable before any teaching starts.
      router.push(`/session/${session_id}/welcome`);
    } catch (err: unknown) {
      setError(err instanceof Error ? errorText(err.message) : t.home.pipelineFailed);
      setStep("failed");
    }
  };

  const handleGoalDone = (_sessionId: string, newGoal: Record<string, string>) => {
    setGoal(newGoal);
    startSession(newGoal);
  };

  // The landing block sits above the geometric centre (concept §8.2) — optical
  // centring, since the eye reads a short centred block as sitting low. Only the
  // `repo` step: the interview, the progress screen and the failure state are all
  // taller, and pushing those up would crowd them against the top on a laptop.
  //
  // The value is measured rather than chosen. `justify-center` centres within the
  // PADDED box, so the bottom padding is what moves the block, and the first
  // guess (16vh) moved the centre only from 50% to 46% — a shift too small to
  // read as deliberate. At 28vh the 381px block centres at 40.4% on a 720px
  // viewport, 39.6% at 900px and 41.0% at 640px, and still fits at all three.
  // Below ~620px it stops fitting, main grows past the viewport and the page
  // scrolls, which is the right way for this to fail.
  //
  // Written as one class per step rather than an override, because Tailwind
  // resolves conflicts by stylesheet order, not class order — `pb-[28vh]` after
  // `py-16` would be a coin toss (see the note in `ui/Button.tsx`).
  const vertical = step === "repo" ? "pt-16 pb-[28vh]" : "py-16";

  return (
    <main className={`relative flex min-h-screen flex-col items-center justify-center bg-ink px-6 ${vertical}`}>
      {/* There is no chrome on this page to sit in, so it floats in the corner
          the session header's copy occupies. */}
      <SettingsMenu className="absolute end-5 top-5" />

      <div className="mb-14 flex flex-col items-center gap-2 text-center">
        {/* The one piece of ornament in the product, and it is a geometric
            primitive rather than a picture: a filled square turned 45°. It marks
            the wordmark here and is planned beside it in the session header
            (concept §8.2). Left inline until that second call site exists —
            extracting a primitive for one use would be the speculative kind. */}
        <span aria-hidden className="mb-3 h-2 w-2 rotate-45 bg-signal" />
        <h1 className="font-display text-display font-medium tracking-tight text-chalk">
          {t.appName}
        </h1>
        <p className="max-w-sm text-aside text-graphite">
          {t.tagline}
        </p>
      </div>

      {step === "repo" && (
        <form onSubmit={handleRepoSubmit} className="flex w-full max-w-md flex-col gap-3">
          <label
            htmlFor="repo"
            className="font-mono text-micro uppercase tracking-[0.14em] text-graphite"
          >
            {t.home.repoLabel}
          </label>
          <input
            id="repo"
            type="url"
            className="rounded-field border border-rule bg-trench px-3.5 py-3 text-start font-mono text-aside text-chalk placeholder:text-graphite focus:border-signal-dim"
            placeholder={t.home.repoPlaceholder}
            value={repoUrl}
            onChange={(e) => { setRepoUrl(e.target.value); setError(null); }}
            required
          />

          {error && <p className="text-aside text-rust">{error}</p>}

          <Button variant="primary" size="block" className="mt-1"
            type="submit"
            disabled={checking}
          >
            {checking ? t.home.checking : t.home.start}
          </Button>

          {/* Below the action, not above it: the sequence reads repo → start →
              what that costs you. Recents follow, because they are a shortcut
              back into the field and only matter to someone who has been here
              before — a returning user looks for them, a new one should not have
              to step over them to reach the button. */}
          <p className="mt-2 text-meta text-graphite">{t.home.expectation}</p>

          {recent.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
                {t.home.recent}
              </span>
              {recent.map((url) => (
                <Button variant="chrome" size="xs"
                  key={url}
                  type="button"
                  onClick={() => { setRepoUrl(url); setError(null); }}
                >
                  {url.replace(/^https?:\/\/github\.com\//, "")}
                </Button>
              ))}
            </div>
          )}
        </form>
      )}

      {step === "goal" && <GoalDialogue repoUrl={repoUrl} onDone={handleGoalDone} />}

      {step === "starting" && (
        <StartingProgress repoUrl={repoUrl} progressId={progressId} goal={startedGoal} />
      )}

      {step === "failed" && (
        <div className="flex w-full max-w-md flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <span className="font-mono text-micro uppercase tracking-[0.14em] text-rust">
              {t.failed.label}
            </span>
            <h2 className="font-display text-head font-medium tracking-tight text-chalk">
              {repoUrl.replace(/^https?:\/\/github\.com\//, "")}
            </h2>
            <p className="text-aside text-graphite">
              {t.failed.reassurance}
            </p>
          </div>

          {error && (
            <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words rounded-field border border-rule bg-trench p-3 font-mono text-micro text-rust">
              {error}
            </pre>
          )}

          <div className="flex flex-wrap gap-3">
            <Button variant="primary" size="md"
              onClick={() => goal && startSession(goal)}
              disabled={!goal}
            >
              {t.failed.tryAgain}
            </Button>
            <Button variant="secondary" size="md"
              onClick={() => { setStep("repo"); setError(null); setGoal(null); }}
            >
              {t.failed.differentRepo}
            </Button>
            {/* A failed run must not be a dead end. The learner's other
                sessions are still there, and this is the way back to them. */}
            <Button variant="chrome" size="md" onClick={() => router.push("/sessions")}>
              {t.dashboard.backToDashboard}
            </Button>
          </div>
        </div>
      )}
    </main>
  );
}
