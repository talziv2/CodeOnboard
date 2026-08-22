"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Button from "@/components/ui/Button";
import { destinationFor } from "@/lib/auth-redirect";
import { NEXT_PARAM, useAuth } from "@/lib/auth";
import { errorText, t } from "@/lib/strings";

/**
 * Sign in and sign up. One component, because they are one form with one extra
 * field and one different verb — and two components would be two places for the
 * "where do I go afterwards" logic to drift.
 */
export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const { signIn, signUp } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const copy = mode === "login" ? t.auth.login : t.auth.signup;

  // Where to land afterwards. `destinationFor` is the open-redirect guard, kept
  // as a pure function in `lib/auth-redirect` so it can be tested directly —
  // the hazard is one wrong character wide.
  const destination = () => destinationFor(params.get(NEXT_PARAM));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") await signIn(email.trim(), password);
      else await signUp(email.trim(), password, displayName.trim() || undefined);
      router.replace(destination());
    } catch (err: unknown) {
      setError(err instanceof Error ? errorText(err.message) : copy.failed);
      setBusy(false);
    }
  };

  return (
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

      <label
        htmlFor="password"
        className="mt-1 font-mono text-micro uppercase tracking-[0.14em] text-graphite"
      >
        {t.auth.passwordLabel}
      </label>
      <input
        id="password"
        type="password"
        /* `new-password` on signup tells a password manager to OFFER one rather
           than autofill an existing credential into what is a new account. */
        autoComplete={mode === "login" ? "current-password" : "new-password"}
        required
        className="rounded-field border border-rule bg-trench px-3.5 py-3 text-start font-mono text-aside text-chalk placeholder:text-graphite focus:border-signal-dim"
        value={password}
        onChange={(e) => { setPassword(e.target.value); setError(null); }}
      />
      {mode === "signup" && (
        <p className="text-meta text-graphite">{t.auth.passwordHint}</p>
      )}

      {mode === "signup" && (
        <>
          <label
            htmlFor="display-name"
            className="mt-1 font-mono text-micro uppercase tracking-[0.14em] text-graphite"
          >
            {t.auth.nameLabel}
          </label>
          <input
            id="display-name"
            type="text"
            autoComplete="name"
            className="rounded-field border border-rule bg-trench px-3.5 py-3 text-start font-mono text-aside text-chalk placeholder:text-graphite focus:border-signal-dim"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
        </>
      )}

      {error && <p role="alert" className="text-aside text-rust">{error}</p>}

      <Button variant="primary" size="block" className="mt-2" type="submit" disabled={busy}>
        {busy ? copy.busy : copy.submit}
      </Button>

      <p className="mt-2 text-center text-meta text-graphite">
        {copy.switchPrompt}{" "}
        <a
          className="text-chalk underline decoration-rule underline-offset-4 hover:decoration-signal"
          href={mode === "login" ? "/signup" : "/login"}
        >
          {copy.switchAction}
        </a>
      </p>
    </form>
  );
}
