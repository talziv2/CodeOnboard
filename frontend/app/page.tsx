"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import GoalDialogue from "@/components/GoalDialogue";
import { sessionStart } from "@/lib/api";

type Step = "repo" | "goal" | "starting";

export default function Home() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("repo");
  const [repoUrl, setRepoUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleRepoSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim()) return;
    setError(null);
    setStep("goal");
  };

  const handleGoalDone = async (
    _sessionId: string,
    goal: Record<string, string>
  ) => {
    setStep("starting");
    try {
      const { session_id } = await sessionStart(repoUrl, goal);
      router.push(`/session/${session_id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to start session");
      setStep("goal");
    }
  };

  return (
    <main className="min-h-screen bg-gray-950 flex flex-col items-center justify-center px-4">
      <div className="mb-10 text-center">
        <h1 className="text-4xl font-bold text-white tracking-tight">CodeOnboard</h1>
        <p className="text-gray-400 mt-2 text-lg">AI-powered codebase onboarding</p>
      </div>

      {step === "repo" && (
        <form
          onSubmit={handleRepoSubmit}
          className="flex flex-col gap-4 w-full max-w-md"
        >
          <label className="text-gray-300 font-medium">GitHub repository URL</label>
          <input
            type="url"
            className="rounded-lg bg-gray-800 border border-gray-600 text-white px-4 py-3 focus:outline-none focus:border-indigo-500"
            placeholder="https://github.com/psf/requests"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            required
          />
          {error && <p className="text-red-400 text-sm">{error}</p>}
          <button
            type="submit"
            className="rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium py-3 transition"
          >
            Start →
          </button>
        </form>
      )}

      {step === "goal" && (
        <GoalDialogue repoUrl={repoUrl} onDone={handleGoalDone} />
      )}

      {step === "starting" && (
        <p className="text-gray-400 animate-pulse text-lg">
          Building your learning path… this may take a minute.
        </p>
      )}
    </main>
  );
}
