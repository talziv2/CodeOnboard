"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { t } from "@/lib/strings";

/**
 * The front door is now a signpost, not a destination.
 *
 * Signed in, the useful landing place is the dashboard — "what was I working
 * on" is the question a returning learner actually has, and it is the one the
 * product could not answer at all before accounts. Signed out, it is the login
 * screen.
 *
 * The repo-and-interview flow that used to live here moved to `/new`
 * unchanged, because starting a session is now one thing a learner does rather
 * than the only thing.
 */
export default function Home() {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "authenticated") router.replace("/sessions");
    else if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-ink">
      <p className="animate-pulse font-mono text-aside text-graphite">
        {t.auth.checking}
      </p>
    </main>
  );
}
