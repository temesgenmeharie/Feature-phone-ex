import { FormEvent, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "../lib/api";
import { useLabStore } from "../store/useAuthStore";

interface CaseItem {
  id: number;
  case_number: string;
  title: string;
  purpose: string;
  status: string;
}

export function NewExaminationPage() {
  const qc = useQueryClient();
  const { token, activeCaseId, setActiveCaseId } = useLabStore();
  const [form, setForm] = useState({
    case_number: "",
    title: "",
    purpose: "",
    device_owner_ref: "",
    device_description: "",
    notes: "",
  });
  const [feedback, setFeedback] = useState<string | null>(null);

  const { data: cases = [] } = useQuery({
    queryKey: ["cases"],
    queryFn: () => apiFetch<CaseItem[]>("/cases", {}, token),
    enabled: !!token,
  });

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setFeedback(null);
    const created = await apiFetch<CaseItem>("/cases", { method: "POST", body: JSON.stringify(form) }, token);
    setActiveCaseId(created.id);
    setFeedback(`Case ${created.case_number} created and selected as active.`);
    setForm({ case_number: "", title: "", purpose: "", device_owner_ref: "", device_description: "", notes: "" });
    await qc.invalidateQueries({ queryKey: ["cases"] });
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <form onSubmit={onSubmit} className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
        <h2 className="text-xl font-semibold">New Forensic Examination Case</h2>
        {feedback && <div className="rounded bg-emerald-950/70 border border-emerald-800 px-3 py-2 text-sm text-emerald-300">{feedback}</div>}
        {[
          ["case_number", "Case Number (e.g. CASE-2026-010)", true],
          ["title", "Case Title", true],
          ["purpose", "Examination Purpose", true],
          ["device_owner_ref", "Device Owner / Reference", false],
          ["device_description", "Device Description", false],
        ].map(([key, label, req]) => (
          <div key={String(key)}>
            <label className="block text-xs text-slate-400 mb-1">{label}</label>
            <input
              required={Boolean(req)}
              value={form[key as keyof typeof form]}
              onChange={(e) => setForm({ ...form, [key as string]: e.target.value })}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            />
          </div>
        ))}
        <div>
          <label className="block text-xs text-slate-400 mb-1">Examination Notes</label>
          <textarea
            rows={3}
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          />
        </div>
        <button type="submit" className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium hover:bg-sky-500">
          Create Examination Case
        </button>
      </form>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-3">
        <h3 className="text-lg font-semibold">Select Active Examination Case</h3>
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {cases.map((c) => (
            <button
              key={c.id}
              onClick={() => setActiveCaseId(c.id)}
              className={`w-full text-left rounded-lg border px-4 py-3 text-sm transition ${
                activeCaseId === c.id ? "border-sky-500 bg-sky-950/40" : "border-slate-800 bg-slate-950/60 hover:border-slate-700"
              }`}
            >
              <div className="flex justify-between font-medium">
                <span className="font-mono text-sky-300">{c.case_number}</span>
                <span className="text-xs uppercase text-slate-400">{c.status}</span>
              </div>
              <p className="text-slate-200">{c.title}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

