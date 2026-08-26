"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import GoalDialogue from "@/components/GoalDialogue";
import SettingsMenu from "@/components/SettingsMenu";
import StartingProgress from "@/components/StartingProgress";
import { checkRepo, getSessionSummary, sessionStart } from "@/lib/api";
import Button from "@/components/ui/Button";
import { errorText, t } from "@/lib/strings";

type Step = "repo" | "goal" | "starting" | "failed";

const RECENT_KEY = "codeonboard:recent-repos";

/**
 * How often to ask whether the plan has landed.
 *
 * Slower than `StartingProgress`'s own poll (900ms), because the two are asking
 * different things: that one draws a live activity line and wants to look alive,
 * this one waits for a single transition in a two-to-four-minute job. Matched to
 * the dashboard's interval, which watches the same rows for the same reason.
 */
const SESSION_POLL_MS = 4000;

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
  // The session being planned, once the id exists. Set for the whole wait, which
  // is what keeps the learner on the progress screen instead of the dashboard.
  const [waitingFor, setWaitingFor] = useState<string | null>(null);
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
      // M7 made this call RETURN AT ONCE — the plan is built by a background
      // task — and the first cut of that took the learner to the dashboard the
      // moment the id existed. That threw away the wrong half of the change.
      //
      // What M7 fixed is that the SESSION no longer depends on the tab staying
      // open: the row is reserved before any work starts, so closing the tab
      // loses nothing. What it did not change is that this learner is still
      // waiting for THIS route, and the progress screen is the only place that
      // says what is being read, in their repository, on their goal. Redirecting
      // replaced a screen full of real streamed facts with a card that says
      // "Building your route…".
      //
      // So: stay, and watch. `waitingFor` starts the poll below; the dashboard
      // still shows the same session building, for a learner who leaves.
      setWaitingFor(session_id);
    } catch (err: unknown) {
      setError(err instanceof Error ? errorText(err.message) : t.home.pipelineFailed);
      setStep("failed");
    }
  };

  /**
   * Watch the reserved session until its plan lands.
   *
   * TWO SOURCES, and they answer different questions. `StartingProgress` polls
   * the RUN — what is being read, which stage, how long — and a run that has
   * ended stops reporting. This polls the SESSION ROW, which is the only thing
   * that says whether the plan was written: `active` means there is a route to
   * walk, `failed` means the background task gave up. Neither is derivable from
   * the other, which is why the redirect could not simply be deleted.
   *
   * A poll that errors is treated as no news. The row is written by a background
   * task and a blip must not be reported as a failed pipeline — the terminal
   * status is the authority, and it is guaranteed to arrive (`_generate_session`
   * leaves the row in a terminal state on every path).
   */
  useEffect(() => {
    if (!waitingFor) return;
    let live = true;
    const check = async () => {
      try {
        const summary = await getSessionSummary(waitingFor);
        if (!live) return;
        if (summary.status === "active") {
          // Land on the welcome page, not the first lesson: after a wait this
          // long, the first thing owed is what the repository is and what the
          // system took the goal to be — both checkable before any teaching
          // starts.
          router.push(`/session/${waitingFor}/welcome`);
        } else if (summary.status === "failed") {
          setWaitingFor(null);
          setError(t.home.pipelineFailed);
          setStep("failed");
        }
      } catch {
        /* No news. See above. */
      }
    };
    check();
    const timer = setInterval(check, SESSION_POLL_MS);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [waitingFor, router]);

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
