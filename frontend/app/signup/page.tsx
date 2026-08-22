"use client";

import { Suspense } from "react";
import AuthForm from "@/components/auth/AuthForm";
import AuthShell from "@/components/auth/AuthShell";
import { t } from "@/lib/strings";

/**
 * `useSearchParams` (for `?next=`) requires a Suspense boundary in the App
 * Router, or the build fails with a prerender error rather than a runtime one.
 */
export default function SignupPage() {
  return (
    <AuthShell title={t.auth.signup.title} subtitle={t.auth.signup.subtitle}>
      <Suspense fallback={null}>
        <AuthForm mode="signup" />
      </Suspense>
    </AuthShell>
  );
}
