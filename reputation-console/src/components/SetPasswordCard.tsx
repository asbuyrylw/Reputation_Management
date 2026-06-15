"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

// Shared card for the invite-accept + password-reset flows: reads the single-use token from
// the URL (?token=...), takes a new password, posts it, then sends the user to sign in.
export function SetPasswordCard({
  endpoint,
  title,
  cta,
  errorMsg,
}: {
  endpoint: string;
  title: string;
  cta: string;
  errorMsg: string;
}) {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setToken(new URLSearchParams(window.location.search).get("token") ?? "");
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) return setError("Password must be at least 8 characters.");
    if (password !== confirm) return setError("Passwords don't match.");
    setBusy(true);
    try {
      await apiFetch(endpoint, { method: "POST", body: { token, password } });
      router.replace("/login?welcome=1");
    } catch {
      setError(errorMsg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-1 items-center justify-center p-4">
      <form onSubmit={onSubmit} className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold text-gray-900">{title}</h1>
        {!token && (
          <p className="mt-2 text-sm text-red-600">Missing token — use the link from your email.</p>
        )}
        <label className="mt-6 block text-sm font-medium text-gray-700" htmlFor="pw">New password</label>
        <input
          id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          required minLength={8} autoComplete="new-password"
          className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-gray-500 focus:outline-none"
        />
        <label className="mt-4 block text-sm font-medium text-gray-700" htmlFor="cf">Confirm password</label>
        <input
          id="cf" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)}
          required autoComplete="new-password"
          className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-gray-500 focus:outline-none"
        />
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        <button
          type="submit" disabled={busy || !token}
          className="mt-6 w-full rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
        >
          {busy ? "Saving…" : cta}
        </button>
      </form>
    </div>
  );
}
