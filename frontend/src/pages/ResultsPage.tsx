import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { apiFetch } from "../lib/api";
import { useLabStore } from "../store/useAuthStore";

type Tab = "contacts" | "sms" | "missed" | "received" | "dialed" | "sim" | "logs";

export function ResultsPage() {
  const { token, activeAcquisitionId } = useLabStore();
  const [tab, setTab] = useState<Tab>("contacts");
  const [search, setSearch] = useState("");
  const [verifyMsg, setVerifyMsg] = useState<string | null>(null);

  const acqId = activeAcquisitionId;

  const { data: contacts } = useQuery({
    queryKey: ["contacts", acqId, search],
    queryFn: () => apiFetch<{ total: number; items: Array<Record<string, unknown>> }>(`/acquisitions/${acqId}/contacts?search=${encodeURIComponent(search)}`, {}, token),
    enabled: !!token && !!acqId && tab === "contacts",
  });

  const { data: sms } = useQuery({
    queryKey: ["sms", acqId, search],
    queryFn: () => apiFetch<{ total: number; items: Array<Record<string, unknown>> }>(`/acquisitions/${acqId}/sms?search=${encodeURIComponent(search)}`, {}, token),
    enabled: !!token && !!acqId && tab === "sms",
  });

  const { data: calls } = useQuery({
    queryKey: ["calls", acqId, tab, search],
    queryFn: () => apiFetch<{ total: number; items: Array<Record<string, unknown>> }>(`/acquisitions/${acqId}/calls?call_type=${tab}&search=${encodeURIComponent(search)}`, {}, token),
    enabled: !!token && !!acqId && (tab === "missed" || tab === "received" || tab === "dialed"),
  });

  const { data: sim } = useQuery({
    queryKey: ["sim", acqId],
    queryFn: () => apiFetch<Record<string, unknown>>(`/acquisitions/${acqId}/sim`, {}, token),
    enabled: !!token && !!acqId && tab === "sim",
  });

  const { data: logs } = useQuery({
    queryKey: ["logs", acqId],
    queryFn: () => apiFetch<Array<Record<string, unknown>>>(`/acquisitions/${acqId}/logs`, {}, token),
    enabled: !!token && !!acqId && tab === "logs",
  });

  async function verifyHashes() {
    if (!acqId) return;
    const res = await apiFetch<{ all_passed: boolean; results: Array<unknown> }>(`/acquisitions/${acqId}/verify`, { method: "POST" }, token);
    setVerifyMsg(res.all_passed ? `SHA-256 Verification PASSED (${res.results.length} files)` : "WARNING: SHA-256 Verification FAILED!");
  }

  if (!acqId) {
    return <div className="text-slate-400">Complete or select an acquisition first to examine extracted records.</div>;
  }

  const tabs: Array<[Tab, string]> = [
    ["contacts", "Contacts"],
    ["sms", "SMS Messages"],
    ["missed", "Missed Calls"],
    ["received", "Received Calls"],
    ["dialed", "Dialed Calls"],
    ["sim", "SIM Info"],
    ["logs", "Acquisition Logs"],
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-semibold">Examination Results (Acquisition #{acqId})</h2>
        <button onClick={verifyHashes} className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-3 py-2 text-xs font-medium hover:bg-emerald-600">
          <ShieldCheck className="h-4 w-4" /> Verify SHA-256 Integrity
        </button>
      </div>

      {verifyMsg && <div className="rounded-lg border border-emerald-800 bg-emerald-950/60 px-4 py-2 text-sm text-emerald-200">{verifyMsg}</div>}

      <div className="flex flex-wrap gap-2 border-b border-slate-800 pb-2">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${tab === id ? "bg-sky-600 text-white" : "bg-slate-900 text-slate-300 hover:bg-slate-800"}`}
          >
            {label}
          </button>
        ))}
        <input
          placeholder="Search number, name, content..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="ml-auto rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs"
        />
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 overflow-x-auto">
        {tab === "contacts" && (
          <table className="w-full text-left text-xs">
            <thead className="text-slate-400 border-b border-slate-800">
              <tr><th className="py-2">Idx</th><th>Storage</th><th>Name</th><th>Phone Number</th></tr>
            </thead>
            <tbody>
              {(contacts?.items ?? []).map((c, i) => (
                <tr key={i} className="border-b border-slate-800/50">
                  <td className="py-2">{String(c.record_index ?? "Unavailable")}</td>
                  <td className="font-mono">{String(c.storage_location)}</td>
                  <td>{String(c.name ?? "Unavailable")}</td>
                  <td className="font-mono">{String(c.phone_number)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {tab === "sms" && (
          <table className="w-full text-left text-xs">
            <thead className="text-slate-400 border-b border-slate-800">
              <tr><th className="py-2">Storage</th><th>Status</th><th>Party</th><th>Timestamp</th><th>Content</th></tr>
            </thead>
            <tbody>
              {(sms?.items ?? []).map((m, i) => (
                <tr key={i} className="border-b border-slate-800/50">
                  <td className="py-2 font-mono">{String(m.storage_location)}</td>
                  <td>{String(m.status ?? "Unavailable")}</td>
                  <td className="font-mono">{String(m.sender_or_recipient ?? "Unavailable")}</td>
                  <td>{String(m.timestamp_raw ?? "Unavailable")}</td>
                  <td>{String(m.content ?? "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {(tab === "missed" || tab === "received" || tab === "dialed") && (
          <div className="space-y-2">
            <p className="text-xs text-amber-300">Note: Call records from AT+CPBR are limited handset call logs, not network-generated CDRs.</p>
            <table className="w-full text-left text-xs">
              <thead className="text-slate-400 border-b border-slate-800">
                <tr><th className="py-2">Storage</th><th>Number</th><th>Name</th><th>Timestamp</th><th>Duration</th></tr>
              </thead>
              <tbody>
                {(calls?.items ?? []).map((r, i) => (
                  <tr key={i} className="border-b border-slate-800/50">
                    <td className="py-2 font-mono">{String(r.storage_location)}</td>
                    <td className="font-mono">{String(r.phone_number)}</td>
                    <td>{String(r.contact_name ?? "Unavailable")}</td>
                    <td>{String(r.timestamp_raw ?? "Unavailable")}</td>
                    <td>{r.duration_seconds != null ? `${r.duration_seconds}s` : "Unavailable"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "sim" && <pre className="text-xs text-slate-300">{JSON.stringify(sim, null, 2)}</pre>}

        {tab === "logs" && (
          <div className="space-y-1 font-mono text-xs">
            {(logs ?? []).map((l, i) => (
              <div key={i} className="border-b border-slate-800/60 py-1">
                <span className="text-sky-300">{String(l.command)}</span> -&gt; <span className="text-emerald-400">{String(l.terminal_status)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

