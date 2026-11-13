import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  MessageSquare,
  PhoneCall,
  Plug,
  RefreshCw,
  SearchCheck,
  ShieldCheck,
  Unplug,
} from "lucide-react";
import { apiFetch, getDownloadUrl } from "../lib/api";
import { useLabStore } from "../store/useAuthStore";

interface PortInfo {
  port_name: string;
  description: string;
  hwid: string;
  is_simulated: boolean;
  is_usb?: boolean;
  port_type?: string;
}

interface ConnectionStatus {
  connected: boolean;
  port_name: string | null;
  baud_rate: number | null;
  is_simulated: boolean;
  simulator_profile: string | null;
}

interface IdentifyResult {
  device_id: number | null;
  at_ready: boolean;
  manufacturer: string | null;
  model: string | null;
  firmware_revision: string | null;
  imei: string | null;
  sim_status: string | null;
  capabilities: Record<string, { status: string; notes?: string }>;
  unsupported_commands: string[];
  error_detail?: string | null;
}

interface AcquisitionOut {
  id: number;
  acquisition_uid: string;
  status: string;
  tasks: Array<{ category: string; status: string; records_extracted: number }>;
}

interface ExtractedCall {
  id: number;
  call_type: string;
  phone_number: string;
  contact_name: string | null;
  timestamp_raw: string | null;
  duration_seconds: number | null;
  storage_location: string;
  is_cdr_level: boolean;
}

interface ExtractedSms {
  id: number;
  sender_or_recipient: string | null;
  status: string | null;
  timestamp_raw: string | null;
  content: string | null;
  storage_location: string;
}

interface Props {
  onNavigateResults?: () => void;
}

export function DeviceConnectionPage({ onNavigateResults }: Props) {
  const qc = useQueryClient();
  const { token, activeCaseId, setActiveCaseId, setActiveDeviceId, setActiveAcquisitionId } = useLabStore();
  const [selectedPort, setSelectedPort] = useState("");
  const [baudRate, setBaudRate] = useState(115200);
  const [simProfile, setSimProfile] = useState("nokia_105_lab");
  const [ident, setIdent] = useState<IdentifyResult | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Extracted data preview on the same page
  const [extractedAcqId, setExtractedAcqId] = useState<number | null>(null);
  const [extractedCalls, setExtractedCalls] = useState<ExtractedCall[]>([]);
  const [extractedMessages, setExtractedMessages] = useState<ExtractedSms[]>([]);
  const [activeTab, setActiveTab] = useState<"calls" | "messages">("calls");
  const [downloadMsg, setDownloadMsg] = useState<string | null>(null);

  const { data: ports = [], refetch: refetchPorts } = useQuery({
    queryKey: ["ports"],
    queryFn: () => apiFetch<PortInfo[]>("/devices/ports", {}, token),
    enabled: !!token,
  });

  useEffect(() => {
    if (!selectedPort && ports.length > 0) {
      // Prefer USB phone port if present, otherwise simulator, otherwise first available
      const usbPort = ports.find((p) => p.is_usb);
      const chosen = usbPort ?? ports.find((p) => p.is_simulated) ?? ports[0];
      setSelectedPort(chosen.port_name);
    }
  }, [ports, selectedPort]);

  const { data: status } = useQuery({
    queryKey: ["device-status"],
    queryFn: () => apiFetch<ConnectionStatus>("/devices/status", {}, token),
    enabled: !!token,
  });

  const selectedPortInfo = ports.find((p) => p.port_name === selectedPort);
  const isSimulatorPort = selectedPort.startsWith("SIM://");
  const isMotherboardPort = selectedPortInfo?.port_type === "motherboard" || selectedPortInfo?.hwid.includes("PNP0501");

  // Device is considered active and ready only if port is connected AND responded to AT
  const isDeviceActiveAndReady = Boolean(status?.connected && ident?.at_ready && ident?.device_id);

  async function ensureCaseId(): Promise<number> {
    if (activeCaseId) return activeCaseId;
    const stamp = new Date().toISOString().replace(/[-:T.]/g, "").slice(0, 14);
    const created = await apiFetch<{ id: number }>(
      "/cases",
      {
        method: "POST",
        body: JSON.stringify({
          case_number: `CASE-${stamp}`,
          title: "Feature Phone Direct Acquisition",
          purpose: "Logical extraction of calls and messages",
        }),
      },
      token
    );
    setActiveCaseId(created.id);
    return created.id;
  }

  async function handleConnect() {
    setMsg(null);
    setError(null);
    setIdent(null);
    try {
      await apiFetch(
        "/devices/connect",
        {
          method: "POST",
          body: JSON.stringify({
            port_name: selectedPort,
            baud_rate: baudRate,
            use_simulator: isSimulatorPort,
            simulator_profile: simProfile,
          }),
        },
        token
      );
      await qc.invalidateQueries({ queryKey: ["device-status"] });
      setMsg(`Port ${selectedPort} opened. Click 'Identify Device' to test AT responsiveness.`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function handleDisconnect() {
    setMsg(null);
    setError(null);
    try {
      await apiFetch("/devices/disconnect", { method: "POST" }, token);
      setIdent(null);
      await qc.invalidateQueries({ queryKey: ["device-status"] });
      setMsg("Device disconnected safely.");
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function handleIdentify() {
    setMsg(null);
    setError(null);
    setBusy(true);
    try {
      const caseId = await ensureCaseId();
      const res = await apiFetch<IdentifyResult>(
        "/devices/identify",
        { method: "POST", body: JSON.stringify({ case_id: caseId }) },
        token
      );
      setIdent(res);
      if (res.at_ready && res.device_id) {
        setActiveDeviceId(res.device_id);
        const name = [res.manufacturer, res.model].filter(Boolean).join(" ") || "Compatible Feature Phone";
        setMsg(`Device ready: ${name} (IMEI: ${res.imei || "Unavailable"})`);
      } else {
        setError(
          res.error_detail ||
            `No response from ${selectedPort}. Ensure your feature phone is powered ON, USB cable supports data, and USB mode is set to 'COM Port / Modem / PC Suite'.`
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleExtractCallsAndMessages() {
    setMsg(null);
    setError(null);
    setBusy(true);
    try {
      if (!isDeviceActiveAndReady || !ident?.device_id) {
        throw new Error("Cannot extract: device is not active and verified. Please connect and identify the device first.");
      }
      const caseId = await ensureCaseId();

      const acq = await apiFetch<AcquisitionOut>(
        "/acquisitions",
        {
          method: "POST",
          body: JSON.stringify({
            case_id: caseId,
            device_id: ident.device_id,
            categories: ["device_info", "contacts", "sms", "call_history"],
          }),
        },
        token
      );
      setActiveAcquisitionId(acq.id);
      setExtractedAcqId(acq.id);

      // Fetch extracted records directly for immediate display
      const callsRes = await apiFetch<{ items: ExtractedCall[] }>(
        `/acquisitions/${acq.id}/calls?limit=200`,
        {},
        token
      );
      const smsRes = await apiFetch<{ items: ExtractedSms[] }>(
        `/acquisitions/${acq.id}/sms?limit=200`,
        {},
        token
      );
      setExtractedCalls(callsRes.items || []);
      setExtractedMessages(smsRes.items || []);

      setMsg(
        `Extraction finished (${acq.status}): ${callsRes.items?.length || 0} call records and ${smsRes.items?.length || 0} messages extracted.`
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function downloadExport(format: "csv" | "json" | "pdf") {
    if (!extractedAcqId) return;
    setDownloadMsg(null);
    try {
      let artifact: { evidence_file_id: number; file_name: string };
      if (format === "pdf") {
        artifact = await apiFetch(`/acquisitions/${extractedAcqId}/reports/pdf`, { method: "POST" }, token);
      } else {
        artifact = await apiFetch(`/acquisitions/${extractedAcqId}/export/${format}`, {}, token);
      }
      const url = getDownloadUrl(artifact.evidence_file_id);
      const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
      if (!res.ok) throw new Error(`Download failed (${res.status})`);
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = artifact.file_name;
      a.click();
      URL.revokeObjectURL(blobUrl);
      setDownloadMsg(`Downloaded ${artifact.file_name}`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Device Connection & Extraction</h2>
          <p className="text-sm text-slate-400">
            Detect real USB feature phones, verify AT readiness, and extract calls and messages into forensic reports
          </p>
        </div>
        <button
          onClick={() => refetchPorts()}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700"
        >
          <RefreshCw className="h-4 w-4" /> Refresh Ports
        </button>
      </div>

      {isMotherboardPort && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-800 bg-amber-950/50 p-3 text-xs text-amber-200">
          <AlertCircle className="h-4 w-4 flex-shrink-0 text-amber-400 mt-0.5" />
          <div>
            <p className="font-semibold">Notice: {selectedPort} is an onboard motherboard serial port (no phone attached).</p>
            <p className="text-amber-300/80">
              Plug your feature phone (Nokia, Tecno, Itel, Samsung) into the PC via a USB data cable, select{" "}
              <strong>"COM Port / Modem / PC Suite"</strong> on the phone screen, and click <strong>Refresh Ports</strong>.
              For lab testing without a physical phone, you can also select the <strong>Simulated Feature Phone</strong>.
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-rose-800 bg-rose-950/60 px-4 py-2 text-sm text-rose-200">
          <AlertCircle className="h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {msg && (
        <div className="flex items-center justify-between rounded-lg border border-sky-800 bg-sky-950/60 px-4 py-2 text-sm text-sky-200">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            <span>{msg}</span>
          </div>
          {onNavigateResults && extractedAcqId && (
            <button
              onClick={onNavigateResults}
              className="rounded bg-sky-600 px-3 py-1 text-xs font-medium text-white hover:bg-sky-500"
            >
              Full Results View
            </button>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Connection Box */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
          <h3 className="font-semibold text-slate-200">1. Serial Port Configuration</h3>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Select Port</label>
            <select
              value={selectedPort}
              onChange={(e) => {
                setSelectedPort(e.target.value);
                setIdent(null);
                setError(null);
                setMsg(null);
              }}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            >
              {ports.map((p) => {
                const badge = p.is_usb ? "[USB PHONE]" : p.is_simulated ? "[SIMULATOR]" : "[MOTHERBOARD]";
                return (
                  <option key={p.port_name} value={p.port_name}>
                    {badge} {p.description}
                  </option>
                );
              })}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Baud Rate (Standard: 115200)</label>
              <select
                value={baudRate}
                onChange={(e) => setBaudRate(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              >
                {[115200, 57600, 38400, 19200, 9600].map((b) => (
                  <option key={b} value={b}>
                    {b} {b === 115200 ? "(Recommended)" : ""}
                  </option>
                ))}
              </select>
            </div>
            {isSimulatorPort && (
              <div>
                <label className="block text-xs text-slate-400 mb-1">Simulator Profile</label>
                <select
                  value={simProfile}
                  onChange={(e) => setSimProfile(e.target.value)}
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
                >
                  <option value="nokia_105_lab">Standard Feature Phone (Full AT Profile)</option>
                  <option value="itel_limited_modem">Restricted Modem (Limited AT Profile)</option>
                </select>
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2 pt-2">
            {!status?.connected ? (
              <button
                onClick={handleConnect}
                disabled={busy || !selectedPort}
                className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium hover:bg-sky-500 disabled:opacity-40"
              >
                <Plug className="h-4 w-4" /> Connect Port
              </button>
            ) : (
              <button
                onClick={handleDisconnect}
                disabled={busy}
                className="inline-flex items-center gap-2 rounded-lg bg-rose-700 px-4 py-2 text-sm font-medium hover:bg-rose-600 disabled:opacity-40"
              >
                <Unplug className="h-4 w-4" /> Disconnect
              </button>
            )}

            <button
              onClick={handleIdentify}
              disabled={busy || !status?.connected}
              className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium disabled:opacity-40 hover:bg-emerald-500"
            >
              <SearchCheck className="h-4 w-4" /> {busy ? "Probing..." : "Identify Device"}
            </button>

            {/* Extraction button: Active ONLY when device is verified and AT-ready */}
            <button
              onClick={handleExtractCallsAndMessages}
              disabled={busy || !isDeviceActiveAndReady}
              title={
                !status?.connected
                  ? "Connect to a port first"
                  : !ident?.at_ready
                  ? "Click 'Identify Device' to verify the phone is responding before extracting"
                  : "Extract phone calls and SMS messages"
              }
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition ${
                isDeviceActiveAndReady && !busy
                  ? "bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-900/40"
                  : "bg-slate-800 text-slate-500 cursor-not-allowed opacity-50"
              }`}
            >
              <PhoneCall className="h-4 w-4" />
              {busy
                ? "Extracting..."
                : isDeviceActiveAndReady
                ? "Extract Calls & Messages"
                : "Extract Calls & Messages (Requires Active Device)"}
            </button>
          </div>
        </div>

        {/* Real Phone Identification Details */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-slate-200">2. Device Identification & Readiness</h3>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase ${
                isDeviceActiveAndReady
                  ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                  : status?.connected
                  ? "bg-amber-950 text-amber-400 border border-amber-800"
                  : "bg-slate-800 text-slate-400"
              }`}
            >
              {isDeviceActiveAndReady
                ? "Ready For Extraction"
                : status?.connected
                ? "Connected (Pending Identification)"
                : "Disconnected"}
            </span>
          </div>

          <div className="text-sm space-y-1.5 text-slate-300">
            <p>
              Port Connection:{" "}
              <span className={status?.connected ? "text-emerald-400 font-mono" : "text-slate-500"}>
                {status?.connected ? `Connected (${status.port_name})` : "Disconnected"}
              </span>
            </p>
            <p>
              Manufacturer:{" "}
              <span className="font-mono font-semibold text-sky-300">
                {ident?.manufacturer || "Unavailable (Identify device first)"}
              </span>
            </p>
            <p>
              Model:{" "}
              <span className="font-mono font-semibold text-sky-300">
                {ident?.model || "Unavailable"}
              </span>
            </p>
            <p>
              Firmware Revision:{" "}
              <span className="font-mono text-slate-400">
                {ident?.firmware_revision || "Unavailable"}
              </span>
            </p>
            <p>
              IMEI:{" "}
              <span className="font-mono text-slate-400">
                {ident?.imei || "Unavailable"}
              </span>
            </p>
            <p>
              SIM Status:{" "}
              <span className="font-mono text-slate-400">
                {ident?.sim_status || "Unavailable"}
              </span>
            </p>
          </div>

          {ident?.at_ready && ident.capabilities && (
            <div className="pt-2 space-y-1">
              <p className="text-xs font-semibold uppercase text-slate-400">Capability Matrix</p>
              {Object.entries(ident.capabilities).map(([cat, cap]) => (
                <div key={cat} className="flex items-center justify-between rounded bg-slate-950 px-3 py-1 text-xs">
                  <span className="font-mono text-slate-300">{cat}</span>
                  <span className={cap.status === "supported" ? "text-emerald-400" : "text-amber-400 font-medium"}>
                    {cap.status.toUpperCase()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Extracted Phone Calls & Messages Display with Format Downloads */}
      {extractedAcqId && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <div>
              <h3 className="text-lg font-semibold text-slate-100">
                3. Extracted Evidence Records (Acquisition #{extractedAcqId})
              </h3>
              <p className="text-xs text-slate-400">
                {extractedCalls.length} call log entries and {extractedMessages.length} messages acquired and preserved with SHA-256 integrity
              </p>
            </div>

            {/* Appropriate File Format Export Buttons */}
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => downloadExport("pdf")}
                className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-500"
              >
                <FileText className="h-3.5 w-3.5" /> Download PDF Report
              </button>
              <button
                onClick={() => downloadExport("csv")}
                className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
              >
                <FileSpreadsheet className="h-3.5 w-3.5 text-emerald-400" /> Export CSV
              </button>
              <button
                onClick={() => downloadExport("json")}
                className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
              >
                <Download className="h-3.5 w-3.5 text-sky-400" /> Export JSON
              </button>
            </div>
          </div>

          {downloadMsg && (
            <div className="rounded bg-sky-950/60 border border-sky-800 px-3 py-1.5 text-xs text-sky-300">
              {downloadMsg}
            </div>
          )}

          {/* Tab switch between Calls and Messages */}
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab("calls")}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition ${
                activeTab === "calls" ? "bg-indigo-600 text-white" : "bg-slate-950 text-slate-400 hover:bg-slate-800"
              }`}
            >
              <PhoneCall className="h-4 w-4" /> Call Records ({extractedCalls.length})
            </button>
            <button
              onClick={() => setActiveTab("messages")}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition ${
                activeTab === "messages" ? "bg-indigo-600 text-white" : "bg-slate-950 text-slate-400 hover:bg-slate-800"
              }`}
            >
              <MessageSquare className="h-4 w-4" /> SMS Messages ({extractedMessages.length})
            </button>
          </div>

          {/* Records Table */}
          <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950">
            {activeTab === "calls" && (
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate-800 bg-slate-900/80 text-slate-400">
                  <tr>
                    <th className="py-2.5 px-3">Call Type</th>
                    <th className="py-2.5 px-3">Storage</th>
                    <th className="py-2.5 px-3">Phone Number</th>
                    <th className="py-2.5 px-3">Contact Name</th>
                    <th className="py-2.5 px-3">Timestamp</th>
                    <th className="py-2.5 px-3">Duration</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {extractedCalls.map((c, i) => (
                    <tr key={i} className="hover:bg-slate-900/40">
                      <td className="py-2 px-3 font-semibold uppercase text-sky-300">{c.call_type}</td>
                      <td className="py-2 px-3 font-mono text-slate-400">{c.storage_location}</td>
                      <td className="py-2 px-3 font-mono text-slate-100">{c.phone_number}</td>
                      <td className="py-2 px-3 text-slate-300">{c.contact_name || "Unavailable"}</td>
                      <td className="py-2 px-3 text-slate-400">{c.timestamp_raw || "Unavailable"}</td>
                      <td className="py-2 px-3 text-slate-400">
                        {c.duration_seconds != null ? `${c.duration_seconds}s` : "Unavailable"}
                      </td>
                    </tr>
                  ))}
                  {extractedCalls.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-4 text-center text-slate-500">
                        No call records extracted on this device.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            )}

            {activeTab === "messages" && (
              <table className="w-full text-left text-xs">
                <thead className="border-b border-slate-800 bg-slate-900/80 text-slate-400">
                  <tr>
                    <th className="py-2.5 px-3">Storage</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3">Party (Sender/Recipient)</th>
                    <th className="py-2.5 px-3">Timestamp</th>
                    <th className="py-2.5 px-3">Message Content</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {extractedMessages.map((m, i) => (
                    <tr key={i} className="hover:bg-slate-900/40">
                      <td className="py-2 px-3 font-mono text-slate-400">{m.storage_location}</td>
                      <td className="py-2 px-3 font-medium text-sky-300">{m.status || "Unavailable"}</td>
                      <td className="py-2 px-3 font-mono text-slate-100">{m.sender_or_recipient || "Unavailable"}</td>
                      <td className="py-2 px-3 text-slate-400">{m.timestamp_raw || "Unavailable"}</td>
                      <td className="py-2 px-3 text-slate-200">{m.content || "[Empty or PDU preserved]"}</td>
                    </tr>
                  ))}
                  {extractedMessages.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-4 text-center text-slate-500">
                        No SMS messages extracted on this device.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
