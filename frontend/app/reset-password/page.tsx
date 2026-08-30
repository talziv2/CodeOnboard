"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import AuthShell from "@/components/auth/AuthShell";
import Button from "@/components/ui/Button";
import { resetPassword } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorTextOr, t } from "@/lib/strings";

/**
 * Finish a reset: the token arrives in `?token=`, the learner supplies the new
 * password, and the server signs this browser in.
 *
 * `useSearchParams` requires a Suspense boundary in the App Router, or the build
 * fails with a prerender error rather than a runtime one — same as `/login` and
 * `/signup`.
 */
export default function ResetPasswordPage() {
  return (
    <AuthShell title={t.auth.reset.title} subtitle={t.auth.reset.subtitle}>
      <Suspense fallback={null}>
        <ResetPasswordForm />
      </Suspense>
    </AuthShell>
  );
}

function ResetPasswordForm() {
  const { refresh } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token");

  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy || !token) return;
    setBusy(true);
    setError(null);
    try {
      await resetPassword(token, password);
      // The response carried a fresh session cookie, so there is no sign-in
      // step. `refresh` is what tells the provider that — without it the app
      // still believes nobody is signed in and bounces straight back to /login.
      await refresh();
      router.replace("/sessions");
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? errorTextOr(err.message, t.auth.reset.failed)
          : t.auth.reset.failed,
      );
      setBusy(false);
    }
  };

  // No token in the URL: a truncated link, or somebody who typed the path. There
  // is nothing to submit, so the form is not offered at all.
  if (!token) {
    return (
      <div className="flex w-full max-w-sm flex-col gap-3">
        <p role="alert" className="text-aside text-rust">
          {t.auth.reset.missingToken}
        </p>
        <a
          className="text-center text-meta text-graphite underline decoration-rule underline-offset-4 hover:text-chalk hover:decoration-signal"
          href="/forgot-password"
        >
          {t.auth.reset.restart}
        </a>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-3">
      <label
        htmlFor="new-password"
        className="font-mono text-micro uppercase tracking-[0.14em] text-graphite"
      >
        {t.auth.reset.newPasswordLabel}
      </label>
      <input
        id="new-password"
        type="password"
        // `new-password`, so a manager offers to generate and store one rather
        // than autofilling the credential being replaced.
        autoComplete="new-password"
        required
        className="rounded-field border border-rule bg-trench px-3.5 py-3 text-start font-mono text-aside text-chalk placeholder:text-graphite focus:border-signal-dim"
        value={password}
        onChange={(e) => { setPassword(e.target.value); setError(null); }}
      />
      <p className="text-meta text-graphite">{t.auth.passwordHint}</p>
      <p className="text-meta text-graphite">{t.auth.reset.revokeNotice}</p>

      {error && <p role="alert" className="text-aside text-rust">{error}</p>}

      <Button variant="primary" size="block" className="mt-2" type="submit" disabled={busy}>
        {busy ? t.auth.reset.busy : t.auth.reset.submit}
      </Button>

      <a
        className="mt-1 text-center text-meta text-graphite underline decoration-rule underline-offset-4 hover:text-chalk hover:decoration-signal"
        href="/login"
      >
        {t.auth.forgot.back}
      </a>
    </form>
  );
}
