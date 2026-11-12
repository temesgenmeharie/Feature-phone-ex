import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, UserPlus } from "lucide-react";
import { apiFetch } from "../lib/api";
import { useLabStore } from "../store/useAuthStore";

interface AuditEntry {
  id: number;
  examiner_id: number | null;
  case_id: number | null;
  acquisition_id: number | null;
  action: string;
  details_json: Record<string, unknown> | null;
  created_at: string;
}

interface ExaminerRow {
  id: number;
  username: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

export function AuditAdminPage() {
  const qc = useQueryClient();
  const { token, examiner } = useLabStore();
  const isAdmin = examiner?.role === "admin";
  const [actionFilter, setActionFilter] = useState("");
  const [form, setForm] = useState({ username: "", full_name: "", email: "", role: "examiner", password: "" });
  const [msg, setMsg] = useState<string | null>(null);

  const { data: audits = [] } = useQuery({
    queryKey: ["audit-logs", actionFilter],
    queryFn: () =>
      apiFetch<AuditEntry[]>(`/audit-logs${actionFilter ? `?action=${encodeURIComponent(actionFilter)}` : ""}`, {}, token),
    enabled: !!token,
  });

  const { data: examiners = [] } = useQuery({
    queryKey: ["examiners"],
    queryFn: () => apiFetch<ExaminerRow[]>("/examiners", {}, token),
    enabled: !!token && isAdmin,
  });

  async function createExaminer(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    await apiFetch("/examiners", { method: "POST", body: JSON.stringify(form) }, token);
    setMsg(`Examiner '${form.username}' created.`);
    setForm({ username: "", full_name: "", email: "", role: "examiner", password: "" });
    await qc.invalidateQueries({ queryKey: ["examiners"] });
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Chain of Custody & Examiner Administration</h2>
        <p className="text-sm text-slate-400">Immutable audit trail and role-based access management</p>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ClipboardList className="h-4 w-4 text-sky-400" />
            <h3 className="font-semibold">Audit Trail</h3>
          </div>
          <input
            placeholder="Filter by action (e.g. HASH_VERIFIED)"
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs"
          />
        </div>
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-slate-400 border-b border-slate-800">
              <tr><th className="py-2">Time (UTC)</th><th>Action</th><th>Examiner</th><th>Case</th><th>Details</th></tr>
            </thead>
            <tbody>
              {audits.map((a) => (
                <tr key={a.id} className="border-b border-slate-800/50">
                  <td className="py-2 text-slate-400">{new Date(a.created_at).toLocaleString()}</td>
                  <td className="font-mono text-sky-300">{a.action}</td>
                  <td>{a.examiner_id ?? "-"}</td>
                  <td>{a.case_id ?? "-"}</td>
                  <td className="font-mono text-slate-400">{a.details_json ? JSON.stringify(a.details_json) : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {isAdmin && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <form onSubmit={createExaminer} className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
            <div className="flex items-center gap-2">
              <UserPlus className="h-4 w-4 text-emerald-400" />
              <h3 className="font-semibold">Create Examiner Account (Admin)</h3>
            </div>
            {msg && <div className="rounded border border-emerald-800 bg-emerald-950/60 px-3 py-2 text-xs text-emerald-300">{msg}</div>}
            <input required placeholder="Username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
            <input required placeholder="Full Name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
            <input placeholder="Email (optional)" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm">
              <option value="examiner">Examiner</option>
              <option value="admin">Administrator</option>
            </select>
            <input required type="password" minLength={8} placeholder="Password (min 8 chars)" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
            <button type="submit" className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-500">
              Add Examiner
            </button>
          </form>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
            <h3 className="font-semibold">Registered Examiners</h3>
            <div className="space-y-2">
              {examiners.map((ex) => (
                <div key={ex.id} className="flex items-center justify-between rounded-lg bg-slate-950 px-3 py-2 text-xs">
                  <div>
                    <p className="font-medium text-slate-200">{ex.full_name} (<span className="font-mono">{ex.username}</span>)</p>
                  </div>
                  <span className="uppercase text-sky-400">{ex.role}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

