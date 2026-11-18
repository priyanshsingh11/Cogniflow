"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ApiError, login } from "@/lib/api";
import { setStoredUser, setToken } from "@/lib/auth";
import { AuthShell, inputCls } from "@/components/auth-shell";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await login({ email, password });
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
      <p className="eyebrow">Welcome back</p>
      <h1 className="display mt-2 text-5xl leading-none">Sign in</h1>
      <form onSubmit={handleSubmit} className="mt-8 grid gap-4">
        <label className="grid gap-1.5 text-[13px] font-medium text-ink-2">
          Email
          <input type="email" required autoComplete="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} />
        </label>
        <label className="grid gap-1.5 text-[13px] font-medium text-ink-2">
          Password
          <input type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} />
        </label>
        {error && (
          <p role="alert" className="rounded-lg border border-fail/30 bg-fail-soft px-3 py-2 text-[13px] text-fail">{error}</p>
        )}
        <button type="submit" disabled={submitting} className="btn-primary mt-1 justify-center disabled:opacity-50">
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="mt-6 text-[13px] text-muted">
        No account yet?{" "}
        <Link href="/signup" className="font-medium text-ink underline decoration-signal decoration-2 underline-offset-4 hover:text-signal">Create one</Link>
      </p>
    </AuthShell>
  );
}
