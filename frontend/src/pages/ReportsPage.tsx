import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText, ShieldCheck } from "lucide-react";
import { apiFetch, getDownloadUrl } from "../lib/api";
import { useLabStore } from "../store/useAuthStore";

interface AcquisitionRow {
  id: number;
  acquisition_uid: string;
  case_id: number;
  status: string;
  started_at: string;
}

interface EvidenceRow {
  id: number;
  file_name: string;
  file_type: string;
  file_size_bytes: number;
  sha256: string | null;
  last_verification_passed: boolean | null;
}

export function ReportsPage() {
  const { token, activeAcquisitionId, setActiveAcquisitionId } = useLabStore();
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const { data: acquisitions = [] } = useQuery({
    queryKey: ["acquisitions"],
    queryFn: () => apiFetch<AcquisitionRow[]>("/acquisitions", {}, token),
    enabled: !!token,
  });

  const targetAcqId = activeAcquisitionId ?? acquisitions[0]?.id ?? null;

  const { data: evidence = [], refetch: refetchEvidence } = useQuery({
    queryKey: ["evidence", targetAcqId],
    queryFn: () => apiFetch<EvidenceRow[]>(`/acquisitions/${targetAcqId}/evidence`, {}, token),
    enabled: !!token && !!targetAcqId,
  });

  async function generatePdf() {
    if (!targetAcqId) return;
    const res = await apiFetch<{ file_name: string }>(`/acquisitions/${targetAcqId}/reports/pdf`, { method: "POST" }, token);
    setStatusMsg(`Generated PDF: ${res.file_name}`);
    await refetchEvidence();
  }

  async function exportFormat(fmt: "csv" | "json") {
    if (!targetAcqId) return;
    const res = await apiFetch<{ file_name: string }>(`/acquisitions/${targetAcqId}/export/${fmt}`, {}, token);
    setStatusMsg(`Exported ${fmt.toUpperCase()}: ${res.file_name}`);
    await refetchEvidence();
  }

  async function verifyAll() {
    if (!targetAcqId) return;
    const res = await apiFetch<{ all_passed: boolean }>(`/acquisitions/${targetAcqId}/verify`, { method: "POST" }, token);
    setStatusMsg(res.all_passed ? "All SHA-256 hashes verified successfully." : "Hash mismatch detected!");
    await refetchEvidence();
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Forensic Reports & Evidence Integrity</h2>
          <p className="text-sm text-slate-400">Generate PDF reports, export CSV/JSON bundles, and verify SHA-256 hashes</p>
        </div>
        <select
          value={targetAcqId ?? ""}
          onChange={(e) => setActiveAcquisitionId(Number(e.target.value))}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
        >
          {acquisitions.map((a) => (
            <option key={a.id} value={a.id}>
              Acquisition #{a.id} ({a.acquisition_uid.slice(0, 8)}) — {a.status}
            </option>
          ))}
        </select>
      </div>

      {statusMsg && <div className="rounded-lg border border-sky-800 bg-sky-950/60 px-4 py-2 text-sm text-sky-200">{statusMsg}</div>}

      <div className="flex flex-wrap gap-3">
        <button onClick={generatePdf} disabled={!targetAcqId} className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium hover:bg-sky-500 disabled:opacity-40">
          <FileText className="h-4 w-4" /> Generate PDF Report
        </button>
        <button onClick={() => exportFormat("csv")} disabled={!targetAcqId} className="inline-flex items-center gap-2 rounded-lg bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700 disabled:opacity-40">
          Export CSV
        </button>
        <button onClick={() => exportFormat("json")} disabled={!targetAcqId} className="inline-flex items-center gap-2 rounded-lg bg-slate-800 px-4 py-2 text-sm hover:bg-slate-700 disabled:opacity-40">
          Export JSON
        </button>
        <button onClick={verifyAll} disabled={!targetAcqId} className="inline-flex items-center gap-2 rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium hover:bg-emerald-600 disabled:opacity-40">
          <ShieldCheck className="h-4 w-4" /> Verify SHA-256 Hashes
        </button>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-400 border-b border-slate-800">
            <tr><th className="py-2">File</th><th>Type</th><th>Size</th><th>SHA-256 Digest</th><th>Verified</th><th>Action</th></tr>
          </thead>
          <tbody>
            {evidence.map((f) => (
              <tr key={f.id} className="border-b border-slate-800/50">
                <td className="py-2 font-mono">{f.file_name}</td>
                <td>{f.file_type}</td>
                <td>{f.file_size_bytes} B</td>
                <td className="font-mono text-slate-400">{f.sha256}</td>
                <td>{f.last_verification_passed === null ? "Pending" : f.last_verification_passed ? "PASS" : "FAIL"}</td>
                <td>
                  <a href={getDownloadUrl(f.id)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sky-400 hover:underline">
                    <Download className="h-3.5 w-3.5" /> Download
                  </a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
