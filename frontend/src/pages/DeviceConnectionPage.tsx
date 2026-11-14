import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
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
  Smartphone,
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
  const [includeSimulator, setIncludeSimulator] = useState(false);
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

  const { data: ports = [], refetch: refetchPorts, isFetching: isRefreshingPorts } = useQuery({
    queryKey: ["ports", includeSimulator],
    queryFn: () =>
      apiFetch<PortInfo[]>(`/devices/ports?include_simulator=${includeSimulator}`, {}, token),
    enabled: !!token,
  });

  const { data: diagnostics, refetch: refetchDiagnostics } = useQuery({
    queryKey: ["device-diagnostics"],
    queryFn: () =>
      apiFetch<{ mass_storage_detected: boolean; message: string | null }>("/devices/diagnostics", {}, token),
    enabled: !!token,
    refetchInterval: 3000,
  });

  async function handleRefreshAll() {
    await Promise.all([refetchPorts(), refetchDiagnostics()]);
  }

  useEffect(() => {
    if (ports.length > 0) {
      // Prioritize physical USB feature phone ports
      const usbPort = ports.find((p) => p.is_usb);
      if (usbPort) {
        setSelectedPort(usbPort.port_name);
      } else if (!selectedPort || !ports.some((p) => p.port_name === selectedPort)) {
        // Fallback to first port if current selected is invalid
        setSelectedPort(ports[0].port_name);
      }
    }
  }, [ports, selectedPort]);

  const { data: status } = useQuery({
    queryKey: ["device-status"],
    queryFn: () => apiFetch<ConnectionStatus>("/devices/status", {}, token),
    enabled: !!token,
  });

  const selectedPortInfo = ports.find((p) => p.port_name === selectedPort);
  const isSimulatorPort = selectedPort.startsWith("SIM://");
  const isMotherboardPort =
    selectedPortInfo?.port_type === "motherboard" ||
    (selectedPortInfo?.hwid || "").includes("PNP0501");
  const hasUsbPhoneDetected = ports.some((p) => p.is_usb);

  // Device is considered active and ready ONLY if port is connected, responded to AT, and registered with device_id
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
          purpose: "Forensic extraction of call history and SMS messages",
        }),
      },
      token
    );
    setActiveCaseId(created.id);
    return created.id;
  }

  // Connect and immediately perform the AT verification handshake
  async function handleConnectAndVerify() {
    setMsg(null);
    setError(null);
    setIdent(null);
    setBusy(true);

    try {
      if (isMotherboardPort && !isSimulatorPort) {
        throw new Error(
          `${selectedPort} is an internal motherboard serial port with no feature phone attached. Please connect your phone via USB cable.`
        );
      }

      // Step 1: Open the serial transport
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

      // Step 2: Immediate AT Handshake & Identification
      const caseId = await ensureCaseId();
      const res = await apiFetch<IdentifyResult>(
        "/devices/identify",
        { method: "POST", body: JSON.stringify({ case_id: caseId }) },
        token
      );

      setIdent(res);

      if (res.at_ready && res.device_id) {
        setActiveDeviceId(res.device_id);
        const phoneName = [res.manufacturer, res.model].filter(Boolean).join(" ") || "Compatible Feature Phone";
        setMsg(`Device connected & AT verified: ${phoneName} (IMEI: ${res.imei || "Unavailable"}). Ready for extraction.`);
      } else {
        // Safe disconnect if phone did not respond to AT
        try {
          await apiFetch("/devices/disconnect", { method: "POST" }, token);
          await qc.invalidateQueries({ queryKey: ["device-status"] });
        } catch {
          // ignore disconnect error
        }
        setError(
          res.error_detail ||
          `No response from ${selectedPort}. Ensure your feature phone is powered ON, USB data cable is connected, and USB mode is set to 'COM Port / Modem / PC Suite'.`
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    setMsg(null);
    setError(null);
    setBusy(true);
    try {
      await apiFetch("/devices/disconnect", { method: "POST" }, token);
      setIdent(null);
      await qc.invalidateQueries({ queryKey: ["device-status"] });
      setMsg("Device disconnected safely.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleIdentify() {
    if (!status?.connected) return;
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
        setMsg(`Device verified: ${name} (IMEI: ${res.imei || "Unavailable"})`);
      } else {
        setError(
          res.error_detail ||
          `Handset did not respond to AT commands on ${selectedPort}. Ensure phone is ON and set to 'COM Port / Modem / PC Suite'.`
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
        throw new Error(
          "Cannot extract: device is not active and verified. Please connect a responsive feature phone first."
        );
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
        `Extraction completed (${acq.status}): ${callsRes.items?.length || 0} call logs and ${smsRes.items?.length || 0} SMS messages acquired with SHA-256 evidence integrity.`
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

  const phoneDisplayName = ident?.at_ready
    ? [ident.manufacturer, ident.model].filter(Boolean).join(" ") || "Real Feature Phone"
    : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Device Connection & Acquisition</h2>
          <p className="text-sm text-slate-400">
            Connect real USB feature phones (Nokia, Tecno, Itel, Samsung), verify AT responsiveness, and extract call logs & SMS messages
          </p>
        </div>
        <button
          onClick={handleRefreshAll}
          disabled={isRefreshingPorts}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${isRefreshingPorts ? "animate-spin" : ""}`} /> Refresh Ports
        </button>
      </div>

      {/* Phone detected in USB Storage Mode Banner */}
      {diagnostics?.mass_storage_detected && (
        <div className="rounded-xl border border-sky-500/50 bg-sky-950/40 p-5 text-xs text-sky-200 shadow-xl shadow-sky-950/50 space-y-3">
          <div className="flex items-center gap-2 font-semibold text-sky-300 text-sm">
            <Smartphone className="h-5 w-5 text-sky-400 shrink-0" />
            <span>H-MOBILE / Spreadtrum Phone Detected in "U Disk" (Mass Storage) Mode</span>
          </div>
          <p className="text-slate-200 leading-relaxed">
            Your phone screen displays <strong>"Charging"</strong> and <strong>"U disk"</strong> because its firmware default hides the AT modem. In "U disk" mode, the phone operates solely as a flash drive and AT command communication is blocked.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1">
            <div className="rounded-lg bg-slate-900/90 p-3.5 border border-slate-800 space-y-1.5">
              <span className="font-semibold text-emerald-400 text-xs uppercase tracking-wider block">Option 1: Phone Menu / UART Setting</span>
              <p className="text-slate-300 text-xs">
                In the phone, open <strong>Menu &rarr; Settings &rarr; Phone Settings</strong> (or <em>Connectivity</em>). Look for <strong>"UART Settings"</strong> or <strong>"USB Mode"</strong> and change it from <em>"U-Disk"</em> to <em>"Modem"</em> or <em>"COM Port"</em>.
              </p>
            </div>

            <div className="rounded-lg bg-slate-900/90 p-3.5 border border-slate-800 space-y-1.5">
              <span className="font-semibold text-amber-400 text-xs uppercase tracking-wider block">Option 2: Dialpad Secret Code</span>
              <p className="text-slate-300 text-xs">
                Unplug USB, go to the dial screen, and type <strong>*#83781#</strong> (or <strong>*#66#</strong>). If Engineer Mode opens, navigate to <em>Debug&Log &rarr; USB</em> and switch to <em>Serial Port / Modem</em>.
              </p>
            </div>

            <div className="rounded-lg bg-slate-900/90 p-3.5 border border-slate-800 space-y-1.5">
              <span className="font-semibold text-cyan-400 text-xs uppercase tracking-wider block">Option 3: Forensic Boot-Key Combo</span>
              <p className="text-slate-300 text-xs">
                Power OFF the phone (pull battery for 5s, put back). Press and <strong>HOLD</strong> the center <strong>OK</strong> key (or Call key), and plug in the USB cable. Windows will detect the chip as a Spreadtrum COM port.
              </p>
            </div>
          </div>

          <div className="flex items-center justify-between pt-1 border-t border-slate-800/80 text-xs text-slate-400">
            <span>After switching, click <strong>"Refresh Ports"</strong> above.</span>
            <span className="text-indigo-300 font-medium">To test extraction immediately, check <em>"Enable Lab Simulator"</em> on the right.</span>
          </div>
        </div>
      )}

      {/* No USB Phone Detected Guidance Banner */}
      {!hasUsbPhoneDetected && !isSimulatorPort && !diagnostics?.mass_storage_detected && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 text-xs text-amber-200">
          <div className="flex items-center gap-2 font-semibold text-amber-300 text-sm mb-1">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            No Real USB Feature Phone Detected
          </div>
          <p>
            Please connect your feature phone (Nokia, Tecno, Itel, Samsung, etc.) using a <strong>USB data cable</strong> and select <strong>"COM Port / Modem / PC Suite"</strong> on the phone screen.
          </p>
          <p className="mt-1 text-amber-300/70">
            Note: <code>COM1</code> is an internal motherboard serial port with no phone attached. Real feature phones appear with a <code>[USB PHONE]</code> tag once connected.
          </p>
        </div>
      )}

      {/* Success Notification */}
      {msg && (
        <div className="flex items-center gap-2 rounded-lg bg-emerald-950 border border-emerald-800 px-4 py-3 text-sm text-emerald-300">
          <CheckCircle2 className="h-5 w-5 shrink-0" />
          <span>{msg}</span>
        </div>
      )}

      {/* Error Notification */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg bg-rose-950 border border-rose-800 px-4 py-3 text-sm text-rose-300">
          <AlertCircle className="h-5 w-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Connection Box */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-slate-200">1. Serial / COM Port Configuration</h3>
            <label className="flex items-center gap-2 text-xs text-slate-400 cursor-pointer">
              <input
                type="checkbox"
                checked={includeSimulator}
                onChange={(e) => setIncludeSimulator(e.target.checked)}
                className="rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-0"
              />
              <span>Enable Lab Simulator</span>
            </label>
          </div>

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
                const badge = p.is_usb
                  ? "[USB PHONE]"
                  : p.is_simulated
                    ? "[SIMULATOR]"
                    : "[NO PHONE ATTACHED]";
                return (
                  <option key={p.port_name} value={p.port_name}>
                    {badge} {p.description}
                  </option>
                );
              })}
              {ports.length === 0 && <option value="">No COM ports detected</option>}
            </select>
            {isMotherboardPort && (
              <p className="mt-1 text-xs text-amber-400">
                ⚠️ {selectedPort} is an internal motherboard port without a phone attached.
              </p>
            )}
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

          <div className="flex flex-wrap items-center gap-2 pt-2">
            {!status?.connected ? (
              <button
                onClick={handleConnectAndVerify}
                disabled={busy || !selectedPort || (isMotherboardPort && !isSimulatorPort)}
                title={
                  isMotherboardPort && !isSimulatorPort
                    ? "COM1 is a motherboard port. Connect a real USB feature phone."
                    : "Connect to serial port and verify AT handshake"
                }
                className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium hover:bg-sky-500 disabled:opacity-40 shadow-sm"
              >
                <Plug className="h-4 w-4" /> {busy ? "Connecting..." : "Connect & Verify Device"}
              </button>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={handleDisconnect}
                  disabled={busy}
                  className="inline-flex items-center gap-2 rounded-lg bg-rose-700 px-4 py-2 text-sm font-medium hover:bg-rose-600 disabled:opacity-40"
                >
                  <Unplug className="h-4 w-4" /> Disconnect
                </button>
                <button
                  onClick={handleIdentify}
                  disabled={busy}
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium disabled:opacity-40 hover:bg-emerald-500"
                >
                  <SearchCheck className="h-4 w-4" /> {busy ? "Probing..." : "Re-Identify"}
                </button>
              </div>
            )}

            {/* Extraction button: strictly active ONLY when device is verified and AT-ready */}
            <button
              onClick={handleExtractCallsAndMessages}
              disabled={busy || !isDeviceActiveAndReady}
              title={
                !status?.connected
                  ? "Connect a real feature phone first"
                  : !ident?.at_ready
                    ? "Verify device AT responsiveness before extracting"
                    : "Extract phone calls and SMS messages"
              }
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition ${isDeviceActiveAndReady && !busy
                ? "bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-900/40"
                : "bg-slate-800 text-slate-500 cursor-not-allowed opacity-50"
                }`}
            >
              <PhoneCall className="h-4 w-4" />
              {busy
                ? "Extracting..."
                : isDeviceActiveAndReady
                  ? `Extract Calls & Messages (${phoneDisplayName})`
                  : "Extract Calls & Messages (Requires Active Device)"}
            </button>
          </div>
        </div>

        {/* Real Phone Identification Details */}
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-slate-200">2. Device Identification & Readiness</h3>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase ${isDeviceActiveAndReady
                ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                : status?.connected
                  ? "bg-amber-950 text-amber-400 border border-amber-800"
                  : "bg-slate-800 text-slate-400"
                }`}
            >
              {isDeviceActiveAndReady
                ? "Ready For Extraction"
                : status?.connected
                  ? "Port Open (Pending AT Handshake)"
                  : "Disconnected"}
            </span>
          </div>

          <div className="text-sm space-y-1.5 text-slate-300">
            <p>
              Port Status:{" "}
              {isDeviceActiveAndReady ? (
                <span className="text-emerald-400 font-mono font-semibold">
                  Connected & Verified ({status?.port_name})
                </span>
              ) : status?.connected ? (
                <span className="text-amber-400 font-mono">
                  Port Open ({status?.port_name}) — Awaiting AT Response
                </span>
              ) : (
                <span className="text-slate-500 font-mono">Disconnected</span>
              )}
            </p>
            <p>
              Manufacturer:{" "}
              <span className="font-mono font-semibold text-sky-300">
                {ident?.manufacturer || (isMotherboardPort ? "Unavailable (No handset on COM1)" : "Unavailable (Connect device)")}
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
              <h3 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
                <Smartphone className="h-5 w-5 text-indigo-400" />
                3. Extracted Evidence Records — {phoneDisplayName || "Acquisition"} (#{extractedAcqId})
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
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition ${activeTab === "calls" ? "bg-indigo-600 text-white" : "bg-slate-950 text-slate-400 hover:bg-slate-800"
                }`}
            >
              <PhoneCall className="h-4 w-4" /> Call Records ({extractedCalls.length})
            </button>
            <button
              onClick={() => setActiveTab("messages")}
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition ${activeTab === "messages" ? "bg-indigo-600 text-white" : "bg-slate-950 text-slate-400 hover:bg-slate-800"
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
                    <th className="py-2.5 px-3">Sender (Calling Party)</th>
                    <th className="py-2.5 px-3">Recipient (Called Party)</th>
                    <th className="py-2.5 px-3">Timestamp</th>
                    <th className="py-2.5 px-3">Duration</th>
                    <th className="py-2.5 px-3">Handset Log Source</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {extractedCalls.map((c, i) => {
                    const remote = c.contact_name ? `${c.contact_name} (${c.phone_number})` : c.phone_number;
                    const isDialed = c.call_type === "dialed";
                    const sender = isDialed ? "Device (Local Handset)" : remote;
                    const recipient = isDialed ? remote : "Device (Local Handset)";

                    return (
                      <tr key={i} className="hover:bg-slate-900/40">
                        <td className="py-2 px-3 font-semibold uppercase text-sky-300">{c.call_type}</td>
                        <td className="py-2 px-3 font-mono text-slate-400">{c.storage_location}</td>
                        <td className="py-2 px-3 font-mono text-emerald-300">{sender}</td>
                        <td className="py-2 px-3 font-mono text-cyan-300">{recipient}</td>
                        <td className="py-2 px-3 text-slate-400">{c.timestamp_raw || "Unavailable"}</td>
                        <td className="py-2 px-3 text-slate-400">
                          {c.duration_seconds != null ? `${c.duration_seconds}s` : "Unavailable"}
                        </td>
                        <td className="py-2 px-3 text-slate-500 italic">Handset Non-Volatile Memory</td>
                      </tr>
                    );
                  })}
                  {extractedCalls.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-4 text-center text-slate-500">
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
                    <th className="py-2.5 px-3">Sender (Originator)</th>
                    <th className="py-2.5 px-3">Recipient (Destination)</th>
                    <th className="py-2.5 px-3">Timestamp</th>
                    <th className="py-2.5 px-3">Message Content</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {extractedMessages.map((m, i) => {
                    const remote = m.sender_or_recipient || "Unknown";
                    const isOutbox =
                      (m.status || "").toUpperCase().includes("STO") ||
                      (m.status || "").toUpperCase().includes("SENT") ||
                      (m.status || "").toUpperCase().includes("UNSENT");
                    const sender = isOutbox ? "Device (Local Handset)" : remote;
                    const recipient = isOutbox ? remote : "Device (Local Handset)";

                    return (
                      <tr key={i} className="hover:bg-slate-900/40">
                        <td className="py-2 px-3 font-mono text-slate-400">{m.storage_location}</td>
                        <td className="py-2 px-3 font-medium text-sky-300">{m.status || "Unavailable"}</td>
                        <td className="py-2 px-3 font-mono text-emerald-300">{sender}</td>
                        <td className="py-2 px-3 font-mono text-cyan-300">{recipient}</td>
                        <td className="py-2 px-3 text-slate-400">{m.timestamp_raw || "Unavailable"}</td>
                        <td className="py-2 px-3 text-slate-200">{m.content || "[Empty or PDU preserved]"}</td>
                      </tr>
                    );
                  })}
                  {extractedMessages.length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-4 text-center text-slate-500">
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
