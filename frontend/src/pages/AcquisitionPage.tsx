import { useState } from "react";
import { Play, Terminal } from "lucide-react";
import { apiFetch } from "../lib/api";
import { useLabStore } from "../store/useAuthStore";

const CATEGORIES = [
  { id: "device_info", label: "Device Information" },
  { id: "contacts", label: "Contacts (Phonebook)" },
  { id: "sms", label: "SMS Messages" },
  { id: "call_history", label: "Call History (AT+CPBR)" },
  { id: "sim_info", label: "SIM Information" },
];

interface AcquisitionResult {
  id: number;
  acquisition_uid: string;
  status: string;
  limitations_json: string[] | null;
  tasks: Array<{ id: number; category: string; status: string; records_extracted: number; details: string | null }>;
}

interface ATLog {
  id: number;
  command: string;
  response: string;
  terminal_status: string;
  duration_ms: number;
}

export function AcquisitionPage() {
  const { token, activeCaseId, activeDeviceId, setActiveAcquisitionId } = useLabStore();
  const [selected, setSelected] = useState<string[]>(CATEGORIES.map((c) => c.id));
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AcquisitionResult | null>(null);
  const [logs, setLogs] = useState<ATLog[]>([]);
  const [error, setError] = useState<string | null>(null);

  function toggleCategory(id: string) {
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  async function startAcquisition() {
    if (!activeCaseId || !activeDeviceId) {
      setError("Select an active Case and Identify a connected Device first.");
      return;
    }
    setError(null);
    setRunning(true);
    try {
      const acq = await apiFetch<AcquisitionResult>(
        "/acquisitions",
        { method: "POST", body: JSON.stringify({ case_id: activeCaseId, device_id: activeDeviceId, categories: selected }) },
        token
      );
      setResult(acq);
      setActiveAcquisitionId(acq.id);
      const logRows = await apiFetch<ATLog[]>(`/acquisitions/${acq.id}/logs`, {}, token);
      setLogs(logRows);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold">Logical Data Acquisition</h2>
        <p className="text-sm text-slate-400">
          Active Case ID: <span className="font-mono text-sky-300">{activeCaseId ?? "None"}</span> | Active Device ID:{" "}
          <span className="font-mono text-sky-300">{activeDeviceId ?? "None"}</span>
        </p>
      </div>

      {error && <div className="rounded-lg border border-rose-800 bg-rose-950/60 px-4 py-2 text-sm text-rose-200">{error}</div>}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
          <h3 className="font-semibold">Select Extraction Categories</h3>
          <div className="space-y-2">
            {CATEGORIES.map((c) => (
              <label key={c.id} className="flex items-center gap-3 rounded-lg bg-slate-950/70 px-3 py-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={selected.includes(c.id)}
                  onChange={() => toggleCategory(c.id)}
                  className="accent-sky-500"
                />
                <span>{c.label}</span>
              </label>
            ))}
          </div>
          <button
            onClick={startAcquisition}
            disabled={running || selected.length === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium hover:bg-sky-500 disabled:opacity-40"
          >
            <Play className="h-4 w-4" /> {running ? "Acquiring..." : "Start Acquisition"}
          </button>

          {result && (
            <div className="pt-3 space-y-2">
              <p className="text-xs font-semibold uppercase text-slate-400">
                Status: <span className="text-emerald-400">{result.status}</span> (UID: {result.acquisition_uid.slice(0, 8)})
              </p>
              {result.tasks.map((t) => (
                <div key={t.id} className="flex justify-between rounded bg-slate-950 px-3 py-1.5 text-xs">
                  <span className="font-mono">{t.category}</span>
                  <span className="text-slate-300">
                    {t.status} ({t.records_extracted})
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-sky-400" />
            <h3 className="font-semibold">AT Command Communication Log</h3>
          </div>
          <div className="h-80 overflow-y-auto rounded-lg bg-slate-950 p-3 font-mono text-xs space-y-2">
            {logs.map((l) => (
              <div key={l.id} className="border-b border-slate-800/80 pb-2">
                <div className="flex justify-between text-sky-300">
                  <span>&gt; {l.command}</span>
                  <span className={l.terminal_status === "OK" ? "text-emerald-400" : "text-amber-400"}>
                    {l.terminal_status} ({l.duration_ms}ms)
                  </span>
                </div>
                <pre className="whitespace-pre-wrap text-slate-400">{l.response.trim()}</pre>
              </div>
            ))}
            {logs.length === 0 && <p className="text-slate-500">Run an acquisition to inspect verbatim AT logs.</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
