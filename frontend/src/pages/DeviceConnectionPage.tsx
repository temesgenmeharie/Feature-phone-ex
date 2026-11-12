import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PhoneCall, Plug, RefreshCw, SearchCheck, Unplug } from "lucide-react";
import { apiFetch } from "../lib/api";
import { useLabStore } from "../store/useAuthStore";

interface PortInfo {
  port_name: string;
  description: string;
  hwid: string;
  is_simulated: boolean;
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
}

interface AcquisitionOut {
  id: number;
  status: string;
  tasks: Array<{ category: string; status: string; records_extracted: number }>;
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

  const { data: ports = [], refetch: refetchPorts } = useQuery({
    queryKey: ["ports"],
    queryFn: () => apiFetch<PortInfo[]>("/devices/ports", {}, token),
    enabled: !!token,
  });

  useEffect(() => {
    if (!selectedPort && ports.length > 0) {
      const physical = ports.find((p) => !p.is_simulated);
      setSelectedPort((physical ?? ports[0]).port_name);
    }
  }, [ports, selectedPort]);

  const { data: status } = useQuery({
    queryKey: ["device-status"],
    queryFn: () => apiFetch<ConnectionStatus>("/devices/status", {}, token),
    enabled: !!token,
  });

  const isSimulatorPort = selectedPort.startsWith("SIM://");

  async function ensureCaseId(): Promise<number> {
    if (activeCaseId) return activeCaseId;
    const stamp = new Date().toISOString().replace(/[-:T.]/g, "").slice(0, 14);
    const created = await apiFetch<{ id: number }>(
      "/cases",
      {
        method: "POST",
        body: JSON.stringify({
          case_number: `CASE-${stamp}`,
          title: "Quick Call History Extraction",
          purpose: "Direct device connection and call-log acquisition",
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
      setMsg(`Connected to ${selectedPort}`);
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
    try {
      const res = await apiFetch<IdentifyResult>(
        "/devices/identify",
        { method: "POST", body: JSON.stringify({ case_id: activeCaseId }) },
        token
      );
      setIdent(res);
      if (res.device_id) setActiveDeviceId(res.device_id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function handleConnectAndExtractCalls() {
    setMsg(null);
    setError(null);
    setBusy(true);
    try {
      const caseId = await ensureCaseId();
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

      const idRes = await apiFetch<IdentifyResult>(
        "/devices/identify",
        { method: "POST", body: JSON.stringify({ case_id: caseId }) },
        token
      );
      setIdent(idRes);
      if (!idRes.device_id) throw new Error("Device identification did not return a device ID.");
      setActiveDeviceId(idRes.device_id);

      const acq = await apiFetch<AcquisitionOut>(
        "/acquisitions",
        {
          method: "POST",
          body: JSON.stringify({
            case_id: caseId,
            device_id: idRes.device_id,
            categories: ["device_info", "call_history"],
          }),
        },
        token
      );
      setActiveAcquisitionId(acq.id);
      const callTask = acq.tasks.find((t) => t.category === "call_history");
      setMsg(
        `Call extraction finished (${callTask?.status ?? acq.status}): ${callTask?.records_extracted ?? 0} call record(s) extracted.`
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Device Connection & Identification</h2>
          <p className="text-sm text-slate-400">Detect USB/COM serial ports, identify the handset, or extract call logs directly</p>
        </div>
        <button
          onClick={() => refetchPorts()}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700"
        >
          <RefreshCw className="h-4 w-4" /> Refresh Ports
        </button>
      </div>

      {error && <div className="rounded-lg border border-rose-800 bg-rose-950/60 px-4 py-2 text-sm text-rose-200">{error}</div>}
      {msg && (
        <div className="flex items-center justify-between rounded-lg border border-sky-800 bg-sky-950/60 px-4 py-2 text-sm text-sky-200">
          <span>{msg}</span>
          {onNavigateResults && msg.includes("Call extraction finished") && (
            <button onClick={onNavigateResults} className="rounded bg-sky-600 px-3 py-1 text-xs font-medium text-white hover:bg-sky-500">
              View Extracted Calls
            </button>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
          <h3 className="font-semibold text-slate-200">Serial Port Configuration</h3>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Serial / COM Port</label>
            <select
              value={selectedPort}
              onChange={(e) => setSelectedPort(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
            >
              {ports.map((p) => (
                <option key={p.port_name} value={p.port_name}>
                  {p.port_name} — {p.description}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Baud Rate</label>
              <select
                value={baudRate}
                onChange={(e) => setBaudRate(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              >
                {[9600, 19200, 38400, 57600, 115200].map((b) => (
                  <option key={b} value={b}>{b}</option>
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
                  <option value="nokia_105_lab">Standard AT Phone (Full Profile)</option>
                  <option value="itel_limited_modem">Restricted Modem (Limited Profile)</option>
                </select>
              </div>
            )}
          </div>

          <div className="flex flex-wrap gap-2 pt-2">
            <button onClick={handleConnect} disabled={busy || !selectedPort} className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium hover:bg-sky-500 disabled:opacity-40">
              <Plug className="h-4 w-4" /> Connect Device
            </button>
            <button onClick={handleConnectAndExtractCalls} disabled={busy || !selectedPort} className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-40">
              <PhoneCall className="h-4 w-4" /> {busy ? "Extracting Calls..." : "Connect & Extract Calls"}
            </button>
            <button onClick={handleIdentify} disabled={busy || !status?.connected} className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium disabled:opacity-40 hover:bg-emerald-500">
              <SearchCheck className="h-4 w-4" /> Identify Device
            </button>
            <button onClick={handleDisconnect} disabled={busy || !status?.connected} className="inline-flex items-center gap-2 rounded-lg bg-rose-700 px-4 py-2 text-sm font-medium disabled:opacity-40 hover:bg-rose-600">
              <Unplug className="h-4 w-4" /> Disconnect
            </button>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
          <h3 className="font-semibold text-slate-200">Connection & Identification Status</h3>
          <div className="text-sm space-y-1 text-slate-300">
            <p>Connection: <span className={status?.connected ? "text-emerald-400 font-semibold" : "text-slate-500"}>{status?.connected ? `Connected (${status.port_name})` : "Disconnected"}</span></p>
            <p>Manufacturer: <span className="font-mono">{ident?.manufacturer ?? "Unavailable"}</span></p>
            <p>Model: <span className="font-mono">{ident?.model ?? "Unavailable"}</span></p>
            <p>Firmware: <span className="font-mono">{ident?.firmware_revision ?? "Unavailable"}</span></p>
            <p>IMEI: <span className="font-mono">{ident?.imei ?? "Unavailable"}</span></p>
          </div>
          {ident && (
            <div className="pt-2 space-y-1">
              <p className="text-xs font-semibold uppercase text-slate-400">Capability Matrix</p>
              {Object.entries(ident.capabilities).map(([cat, cap]) => (
                <div key={cat} className="flex items-center justify-between rounded bg-slate-950 px-3 py-1.5 text-xs">
                  <span className="font-mono">{cat}</span>
                  <span className={cap.status === "supported" ? "text-emerald-400" : "text-amber-400"}>{cap.status.toUpperCase()}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
