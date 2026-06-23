"use client";

import { useState } from "react";
import { useBusiness } from "@/lib/business";
import { useAdminUsers, useCreateUser, useGrantAccess } from "@/lib/hooks";
import { Card, PageHeader, Spinner } from "@/components/ui";
import type { Business } from "@/lib/types";

type GrantMutation = { mutate: (v: { userId: number; business_id: number; access_role: string }) => void; isPending: boolean };

function GrantRow({ userId, businesses, grant }: { userId: number; businesses: Business[]; grant: GrantMutation }) {
  const [bid, setBid] = useState<number | "">("");
  const [ar, setAr] = useState("viewer");
  return (
    <div className="mt-1 flex flex-wrap items-center gap-2">
      <select value={bid} onChange={(e) => setBid(Number(e.target.value))} className="rounded border border-slate-200 px-2 py-1 text-xs">
        <option value="">business…</option>
        {businesses.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name}
          </option>
        ))}
      </select>
      <select value={ar} onChange={(e) => setAr(e.target.value)} className="rounded border border-slate-200 px-2 py-1 text-xs">
        <option value="viewer">viewer</option>
        <option value="editor">editor</option>
      </select>
      <button
        disabled={!bid || grant.isPending}
        onClick={() => bid && grant.mutate({ userId, business_id: Number(bid), access_role: ar })}
        className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100 disabled:opacity-50"
      >
        Grant
      </button>
    </div>
  );
}

export default function UsersPage() {
  const { data, isLoading } = useAdminUsers();
  const { businesses } = useBusiness();
  const createUser = useCreateUser();
  const grant = useGrantAccess();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("client");

  if (isLoading || !data) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Users"
        subtitle="Console accounts. Admins see everything; clients see only the businesses you grant them (viewer = read, editor = can act)."
      />
      <Card className="mb-4">
        <div className="mb-2 text-sm font-medium text-slate-700">Add user</div>
        <div className="flex flex-wrap items-end gap-2">
          <input placeholder="email" value={email} onChange={(e) => setEmail(e.target.value)} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
          <input placeholder="password (8+ chars)" type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm" />
          <select value={role} onChange={(e) => setRole(e.target.value)} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">
            <option value="client">client</option>
            <option value="admin">admin</option>
          </select>
          <button
            disabled={createUser.isPending || !email || password.length < 8}
            onClick={() => createUser.mutate({ email, password, role }, { onSuccess: () => { setEmail(""); setPassword(""); } })}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            Create
          </button>
        </div>
        {createUser.isError && <p className="mt-2 text-xs text-amber-700">Could not create (the email may already exist).</p>}
      </Card>

      <div className="space-y-2">
        {data.map((u) => (
          <Card key={u.id}>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-900">{u.email}</span>
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">{u.role}</span>
            </div>
            {u.role === "client" && (
              <div className="mt-2">
                <div className="text-xs text-slate-500">
                  Access: {u.access.length === 0 ? "none" : u.access.map((a) => `#${a.business_id} (${a.access_role})`).join(", ")}
                </div>
                <GrantRow userId={u.id} businesses={businesses} grant={grant} />
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
