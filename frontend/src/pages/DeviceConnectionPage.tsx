import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plug, RefreshCw, SearchCheck, Unplug } from "lucide-react";
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

export function DeviceConnectionPage() {
  const qc = useQueryClient();
  const { token, activeCaseId, setActiveDeviceId } = useLabStore();
  const [selectedPort, setSelectedPort] = useState("SIM://FEATURE_PHONE_01");
  const [baudRate, setBaudRate] = useState(115200);
  const [simProfile, setSimProfile] = useState("nokia_105_lab");
  const [ident, setIdent] = useState<IdentifyResult | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const { data: ports = [], refetch: refetchPorts } = useQuery({
    queryKey: ["ports"],
    queryFn: () => apiFetch<PortInfo[]>("/devices/ports", {}, token),
    enabled: !!token,
  });

  const { data: status } = useQuery({
    queryKey: ["device-status"],
    queryFn: () => apiFetch<ConnectionStatus>("/devices/status", {}, token),
    enabled: !!token,
  });

  async function handleConnect() {
    setMsg(null);
    const isSim = selectedPort.startsWith("SIM://");
    await apiFetch(
      "/devices/connect",
      {
        method: "POST",
        body: JSON.stringify({
          port_name: selectedPort,
          baud_rate: baudRate,
          use_simulator: isSim,
          simulator_profile: simProfile,
        }),
      },
      token
    );
    await qc.invalidateQueries({ queryKey: ["device-status"] });
    setMsg(`Connected to ${selectedPort}`);
  }

  async function handleDisconnect() {
    setMsg(null);
    await apiFetch("/devices/disconnect", { method: "POST" }, token);
    setIdent(null);
    await qc.invalidateQueries({ queryKey: ["device-status"] });
    setMsg("Device disconnected safely.");
  }

  async function handleIdentify() {
    setMsg(null);
    const res = await apiFetch<IdentifyResult>(
      "/devices/identify",
      { method: "POST", body: JSON.stringify({ case_id: activeCaseId }) },
      token
    );
    setIdent(res);
    if (res.device_id) setActiveDeviceId(res.device_id);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Device Connection & Identification</h2>
          <p className="text-sm text-slate-400">Detect USB/COM serial ports or use the built-in Feature Phone Simulator</p>
        </div>
        <button
          onClick={() => refetchPorts()}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700"
        >
          <RefreshCw className="h-4 w-4" /> Refresh Ports
        </button>
      </div>

      {msg && <div className="rounded-lg border border-sky-800 bg-sky-950/60 px-4 py-2 text-sm text-sky-200">{msg}</div>}

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
            <div>
              <label className="block text-xs text-slate-400 mb-1">Simulator Profile</label>
              <select
                value={simProfile}
                onChange={(e) => setSimProfile(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
              >
                <option value="nokia_105_lab">Nokia 105 (Full AT)</option>
                <option value="itel_limited_modem">Itel it2160 (Limited Modem)</option>
              </select>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 pt-2">
            <button onClick={handleConnect} className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium hover:bg-sky-500">
              <Plug className="h-4 w-4" /> Connect Device
            </button>
            <button onClick={handleIdentify} disabled={!status?.connected} className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium disabled:opacity-40 hover:bg-emerald-500">
              <SearchCheck className="h-4 w-4" /> Identify Device
            </button>
            <button onClick={handleDisconnect} disabled={!status?.connected} className="inline-flex items-center gap-2 rounded-lg bg-rose-700 px-4 py-2 text-sm font-medium disabled:opacity-40 hover:bg-rose-600">
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
