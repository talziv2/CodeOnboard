"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Button from "@/components/ui/Button";
import { GOOGLE_START, linkGoogle } from "@/lib/api";
import { destinationFor } from "@/lib/auth-redirect";
import { NEXT_PARAM, useAuth } from "@/lib/auth";
import { errorText, t } from "@/lib/strings";

/**
 * Sign in and sign up. One component, because they are one form with one extra
 * field and one different verb — and two components would be two places for the
 * "where do I go afterwards" logic to drift.
 */
export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const { signIn, signUp, refresh } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const copy = mode === "login" ? t.auth.login : t.auth.signup;

  /**
   * The callback sends the browser back here with a hint about what happened.
   *
   * `?link=google` means Google verified an address that already belongs to a
   * password account, and NOTHING was linked — the account's password has to be
   * confirmed first. `?error=` is anything that went wrong, already worded.
   */
  const linking = params.get("link") === "google";
  const oauthError = params.get("error");

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
      if (linking) {
        // Confirming the password for a pending Google link, not signing in.
        // The server links, revokes every other session for that account, and
        // issues this browser a fresh one.
        await linkGoogle(password);
        await refresh();
        router.replace("/sessions");
        return;
      }
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
      {linking && (
        <div className="flex flex-col gap-1.5 rounded-field border border-rule bg-trench p-3.5">
          <span className="font-mono text-micro uppercase tracking-[0.14em] text-graphite">
            {t.auth.linkTitle}
          </span>
          <p className="text-meta text-graphite">{t.auth.linkBody}</p>
        </div>
      )}
      {oauthError && (
        <p role="alert" className="text-aside text-rust">{errorText(oauthError)}</p>
      )}
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
        {busy ? (linking ? t.auth.linkBusy : copy.busy)
              : (linking ? t.auth.linkSubmit : copy.submit)}
      </Button>

      {!linking && (
        <>
          <span className="mt-1 text-center font-mono text-micro uppercase tracking-[0.14em] text-graphite">
            or
          </span>
          {/* A full navigation, not a fetch: the browser has to follow Google's
              redirect, and an XHR cannot. */}
          <a
            href={GOOGLE_START}
            className="rounded-field border border-rule bg-trench px-3.5 py-3 text-center text-aside text-chalk hover:border-signal-dim"
          >
            {t.auth.google}
          </a>
        </>
      )}

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
