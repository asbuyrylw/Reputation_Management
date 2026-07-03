"use client";

import Link from "next/link";
import { useState } from "react";
import { apiFetch } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await apiFetch("/auth/forgot-password", { method: "POST", body: { email } });
    } catch {
      // Always show the same confirmation -- never reveal whether the email exists.
    } finally {
      setSent(true);
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-1 items-center justify-center p-4">
      <form onSubmit={onSubmit} className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">Forgot your password?</h1>
        {sent ? (
          <p className="mt-3 text-sm text-slate-600">
            If an account exists for that email, we&apos;ve sent a reset link. Check your inbox.
          </p>
        ) : (
          <>
            <p className="mt-1 text-sm text-slate-500">We&apos;ll email you a reset link.</p>
            <label className="mt-6 block text-sm font-medium text-slate-700" htmlFor="email">Email</label>
            <input
              id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              required autoComplete="username"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            />
            <button
              type="submit" disabled={busy}
              className="mt-6 w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {busy ? "Sending…" : "Send reset link"}
            </button>
          </>
        )}
        <Link href="/login" className="mt-4 block text-center text-sm text-indigo-600 hover:underline">
          Back to sign in
        </Link>
      </form>
    </div>
  );
}
