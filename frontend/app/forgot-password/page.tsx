"use client";

import { useState } from "react";
import AuthShell from "@/components/auth/AuthShell";
import Button from "@/components/ui/Button";
import { requestPasswordReset } from "@/lib/api";
import { errorTextOr, t } from "@/lib/strings";

/**
 * Ask for a reset link.
 *
 * Not part of `AuthForm`: that component is one form with two verbs, and this is
 * a third with no password field, a different success state and no redirect. A
 * `mode="forgot"` branch would have made every one of its existing conditionals
 * three-way.
 *
 * ## The success state says the same thing for every address
 *
 * The server answers identically whether or not the email has an account, and
 * this page must not undo that by being more specific. So `sent` is shown
 * unconditionally, and the development link — when there is one — appears
 * beneath it as an extra, clearly labelled as a development affordance rather
 * than as how the product works.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [devLink, setDevLink] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const { reset_url } = await requestPasswordReset(email.trim());
      setDevLink(reset_url);
      setSent(true);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? errorTextOr(err.message, t.auth.forgot.failed)
          : t.auth.forgot.failed,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title={t.auth.forgot.title} subtitle={t.auth.forgot.subtitle}>
      {sent ? (
        <div className="flex w-full max-w-sm flex-col gap-3">
          <p className="text-aside text-chalk">{t.auth.forgot.sent}</p>

          {devLink && (
            <div className="flex flex-col gap-2 rounded-field border border-rule bg-trench p-3.5">
              <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
                {t.auth.forgot.devNotice}
              </span>
              {/* A real navigation to a real URL, so the demo is one click and
                  the address bar shows the link somebody would have received. */}
              <a
                href={devLink}
                className="break-all text-aside text-chalk underline decoration-rule underline-offset-4 hover:decoration-signal"
              >
                {t.auth.forgot.devOpen}
              </a>
            </div>
          )}

          <a
            className="mt-1 text-center text-meta text-graphite underline decoration-rule underline-offset-4 hover:text-chalk hover:decoration-signal"
            href="/login"
          >
            {t.auth.forgot.back}
          </a>
        </div>
      ) : (
        <form onSubmit={submit} className="flex w-full max-w-sm flex-col gap-3">
          <label
            htmlFor="email"
            className="font-mono text-micro uppercase tracking-[0.14em] text-graphite"
          >
            {t.auth.emailLabel}
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            className="rounded-field border border-rule bg-trench px-3.5 py-3 text-start font-mono text-aside text-chalk placeholder:text-graphite focus:border-signal-dim"
            value={email}
            onChange={(e) => { setEmail(e.target.value); setError(null); }}
          />

          {error && <p role="alert" className="text-aside text-rust">{error}</p>}

          <Button variant="primary" size="block" className="mt-2" type="submit" disabled={busy}>
            {busy ? t.auth.forgot.busy : t.auth.forgot.submit}
          </Button>

          <a
            className="mt-1 text-center text-meta text-graphite underline decoration-rule underline-offset-4 hover:text-chalk hover:decoration-signal"
            href="/login"
          >
            {t.auth.forgot.back}
          </a>
        </form>
      )}
    </AuthShell>
  );
}
