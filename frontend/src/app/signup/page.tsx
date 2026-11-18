"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, signup } from "@/lib/api";
import { setStoredUser, setToken } from "@/lib/auth";
import { AuthShell, inputCls } from "@/components/auth-shell";

export default function SignupPage() {
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await signup({
        email,
        password,
        display_name: displayName,
      });
      setToken(res.access_token);
      setStoredUser(res.user);
      router.push("/dashboard");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Something went wrong. Try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthShell>
      <p className="eyebrow">Free to start</p>
      <h1 className="display mt-2 text-5xl leading-none">Create your account</h1>
      <p className="mt-3 text-[13.5px] leading-6 text-muted">
        You&apos;ll get a personal organization with a default workspace.
      </p>
      <form onSubmit={handleSubmit} className="mt-8 grid gap-4">
        <label className="grid gap-1.5 text-[13px] font-medium text-ink-2">
          Display name
          <input type="text" required autoComplete="name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} className={inputCls} />
        </label>
        <label className="grid gap-1.5 text-[13px] font-medium text-ink-2">
          Email
          <input type="email" required autoComplete="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} />
        </label>
        <label className="grid gap-1.5 text-[13px] font-medium text-ink-2">
          <span>Password <span className="font-normal text-muted">(min 8 characters)</span></span>
          <input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} />
        </label>
        {error && (
          <p role="alert" className="rounded-lg border border-fail/30 bg-fail-soft px-3 py-2 text-[13px] text-fail">{error}</p>
        )}
        <button type="submit" disabled={submitting} className="btn-primary mt-1 justify-center disabled:opacity-50">
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>
      <p className="mt-6 text-[13px] text-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-ink underline decoration-signal decoration-2 underline-offset-4 hover:text-signal">Sign in</Link>
      </p>
    </AuthShell>
  );
}
