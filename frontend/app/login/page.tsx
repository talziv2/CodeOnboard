"use client";

import { Suspense } from "react";
import AuthForm from "@/components/auth/AuthForm";
import AuthShell from "@/components/auth/AuthShell";
import { t } from "@/lib/strings";

/**
 * `useSearchParams` (for `?next=`) requires a Suspense boundary in the App
 * Router, or the build fails with a prerender error rather than a runtime one.
 */
export default function LoginPage() {
  return (
    <AuthShell title={t.auth.login.title} subtitle={t.auth.login.subtitle}>
      <Suspense fallback={null}>
        <AuthForm mode="login" />
      </Suspense>
    </AuthShell>
  );
}
