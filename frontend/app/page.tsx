"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import GoalDialogue from "@/components/GoalDialogue";
import SettingsMenu from "@/components/SettingsMenu";
import { checkRepo, sessionStart } from "@/lib/api";
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
  const [recent, setRecent] = useState<string[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Kept so a failed pipeline can be retried without redoing the interview.
  const [goal, setGoal] = useState<Record<string, string> | null>(null);

  useEffect(() => setRecent(readRecent()), []);

  useEffect(() => {
    if (step !== "starting") return;
    setElapsed(0);
    const timer = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(timer);
  }, [step]);

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
    setStep("starting");
    setError(null);
    try {
      const { session_id } = await sessionStart(repoUrl, forGoal);
      rememberRepo(repoUrl);
      router.push(`/session/${session_id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? errorText(err.message) : t.home.pipelineFailed);
      setStep("failed");
    }
  };

  const handleGoalDone = (_sessionId: string, newGoal: Record<string, string>) => {
    setGoal(newGoal);
    startSession(newGoal);
  };

  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center bg-ink px-6 py-16">
      {/* There is no chrome on this page to sit in, so it floats in the corner
          the session header's copy occupies. */}
      <SettingsMenu className="absolute end-5 top-5" />

      <div className="mb-12 flex flex-col items-center gap-2 text-center">
        <h1 className="font-display text-[calc(38rem/16)] font-medium leading-none tracking-tight text-chalk">
          {t.appName}
        </h1>
        <p className="max-w-sm text-[calc(13.5rem/16)] leading-relaxed text-graphite">
          {t.tagline}
        </p>
      </div>

      {step === "repo" && (
        <form onSubmit={handleRepoSubmit} className="flex w-full max-w-md flex-col gap-3">
          <label
            htmlFor="repo"
            className="font-mono text-[calc(10.5rem/16)] uppercase tracking-[0.14em] text-graphite"
          >
            {t.home.repoLabel}
          </label>
          <input
            id="repo"
            type="url"
            className="rounded border border-rule bg-trench px-3.5 py-3 text-start font-mono text-[calc(13rem/16)] text-chalk placeholder:text-graphite focus:border-signal-dim focus:outline-none"
            placeholder={t.home.repoPlaceholder}
            value={repoUrl}
            onChange={(e) => { setRepoUrl(e.target.value); setError(null); }}
            required
          />

          {recent.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[calc(10rem/16)] uppercase tracking-[0.14em] text-graphite">
                {t.home.recent}
              </span>
              {recent.map((url) => (
                <button
                  key={url}
                  type="button"
                  onClick={() => { setRepoUrl(url); setError(null); }}
                  className="rounded border border-rule px-2.5 py-1 font-mono text-[calc(11rem/16)] text-graphite transition hover:border-signal-dim hover:text-signal"
                >
                  {url.replace(/^https?:\/\/github\.com\//, "")}
                </button>
              ))}
            </div>
          )}

          {error && <p className="text-[calc(13rem/16)] text-rust">{error}</p>}

          <button
            type="submit"
            disabled={checking}
            className="mt-1 rounded border border-signal-dim bg-signal/15 py-3 text-[calc(13.5rem/16)] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
          >
            {checking ? t.home.checking : t.home.start}
          </button>
        </form>
      )}

      {step === "goal" && <GoalDialogue repoUrl={repoUrl} onDone={handleGoalDone} />}

      {step === "starting" && (
        <div className="flex w-full max-w-md flex-col gap-5">
          <div className="flex flex-col gap-1.5">
            <span className="font-mono text-[calc(10.5rem/16)] uppercase tracking-[0.14em] text-graphite">
              {t.starting.label}
            </span>
            <h2 className="font-display text-[calc(21rem/16)] font-medium tracking-tight text-chalk">
              {repoUrl.replace(/^https?:\/\/github\.com\//, "")}
            </h2>
          </div>

          {/* The backend doesn't stream progress, so these are listed rather
              than checked off — only elapsed time is real. */}
          <ul className="flex flex-col gap-2.5">
            {t.starting.phases.map((phase) => (
              <li key={phase} className="flex items-center gap-2.5 text-[calc(12.5rem/16)] text-graphite">
                <span aria-hidden className="h-[11px] w-[11px] shrink-0 rounded-full border-[1.5px] border-rule" />
                {phase}
              </li>
            ))}
          </ul>

          <div className="flex items-center gap-2.5 border-t border-rule pt-3">
            <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-signal" />
            <span className="font-mono text-[calc(11rem/16)] text-graphite">
              {t.starting.elapsed(elapsed)}
            </span>
          </div>
        </div>
      )}

      {step === "failed" && (
        <div className="flex w-full max-w-md flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <span className="font-mono text-[calc(10.5rem/16)] uppercase tracking-[0.14em] text-rust">
              {t.failed.label}
            </span>
            <h2 className="font-display text-[calc(21rem/16)] font-medium tracking-tight text-chalk">
              {repoUrl.replace(/^https?:\/\/github\.com\//, "")}
            </h2>
            <p className="text-[calc(13rem/16)] leading-relaxed text-graphite">
              {t.failed.reassurance}
            </p>
          </div>

          {error && (
            <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words rounded border border-rule bg-trench p-3 font-mono text-[calc(11rem/16)] leading-relaxed text-rust">
              {error}
            </pre>
          )}

          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => goal && startSession(goal)}
              disabled={!goal}
              className="rounded border border-signal-dim bg-signal/15 px-4 py-2 text-[calc(13rem/16)] font-medium text-signal transition hover:bg-signal/25 disabled:opacity-40"
            >
              {t.failed.tryAgain}
            </button>
            <button
              onClick={() => { setStep("repo"); setError(null); setGoal(null); }}
              className="rounded border border-rule px-4 py-2 text-[calc(13rem/16)] text-graphite transition hover:border-signal-dim hover:text-signal"
            >
              {t.failed.differentRepo}
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
