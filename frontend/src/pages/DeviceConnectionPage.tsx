import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  AlertTriangle,
  Binary,
  CheckCircle2,
  CheckSquare,
  Cpu,
  Database,
  Download,
  Eye,
  FileSearch,
  FileSpreadsheet,
  FileText,
  FolderTree,
  HardDrive,
  Layers,
  ListChecks,
  MessageSquare,
  PhoneCall,
  Plug,
  RefreshCw,
  SearchCheck,
  ShieldCheck,
  Smartphone,
  Square,
  Unplug,
  Usb,
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
  charset?: string | null;
  capabilities: Record<string, { status: string; notes?: string; supported_commands?: string[]; unsupported_commands?: string[] }>;
  storage_stats?: {
    calls?: Record<string, { used: number; total: number }>;
    contacts?: Record<string, { used: number; total: number }>;
    sms?: Record<string, { used: number; total: number }>;
  };
  unsupported_commands: string[];
  error_detail?: string | null;
}

interface DiscoveredArtifact {
  category: string;
  file_name: string;
  file_path: string;
  size_bytes: number;
  estimated_count: number;
  description: string;
  is_deleted_carvable: boolean;
}

interface UDiskPreview {
  drive_letter: string;
  volume_name: string;
  filesystem: string;
  phone_vendor: string | null;
  total_bytes: number;
  free_bytes: number;
  used_bytes: number;
  contacts_count: number;
  sms_count: number;
  calls_count: number;
  carved_candidates_count: number;
  artifacts: DiscoveredArtifact[];
  supported_categories: string[];
  forensic_guarantee: string;
}

interface UDiskDrive {
  drive_letter: string;
  volume_name: string;
  filesystem: string;
  total_bytes: number;
  free_bytes: number;
  phone_vendor: string | null;
  detected_folders: string[];
  is_phone_storage: boolean;
}

interface DriverProblem {
  instance_id: string;
  hardware_id: string;
  device_name: string;
  vendor: string;
  problem_code: number;
  problem_description: string;
  resolution_guide: string;
}

interface DiagnosticReport {
  primary_mode: "COM" | "UDISK" | "COM_DRIVER_MISSING" | "ADB" | "CHARGING_ONLY" | "NO_DEVICE";
  detected_vendor: string | null;
  summary_message: string;
  udisk_drives: UDiskDrive[];
  driver_problem_devices: DriverProblem[];
  charging_detected: boolean;
  mass_storage_detected: boolean;
  message: string | null;
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

  const [selectedUDisk, setSelectedUDisk] = useState<string>("");

  const [selectedCategories, setSelectedCategories] = useState<{
    device_info: boolean;
    contacts: boolean;
    sms: boolean;
    call_history: boolean;
  }>({
    device_info: true,
    contacts: true,
    sms: true,
    call_history: true,
  });

  const toggleCategory = (cat: keyof typeof selectedCategories) => {
    setSelectedCategories((prev) => ({ ...prev, [cat]: !prev[cat] }));
  };

  const selectAllCategories = () => {
    setSelectedCategories({
      device_info: true,
      contacts: true,
      sms: true,
      call_history: true,
    });
  };

  const deselectAllCategories = () => {
    setSelectedCategories({
      device_info: false,
      contacts: false,
      sms: false,
      call_history: false,
    });
  };

  const activeCategoryList = Object.entries(selectedCategories)
    .filter(([_, enabled]) => enabled)
    .map(([k]) => k);

  const { data: ports = [], refetch: refetchPorts, isFetching: isRefreshingPorts } = useQuery({
    queryKey: ["ports", includeSimulator],
    queryFn: () =>
      apiFetch<PortInfo[]>(`/devices/ports?include_simulator=${includeSimulator}`, {}, token),
    enabled: !!token,
  });

  const { data: diagnostics, refetch: refetchDiagnostics } = useQuery({
    queryKey: ["device-diagnostics"],
    queryFn: () =>
      apiFetch<DiagnosticReport>("/devices/diagnostics", {}, token),
    enabled: !!token,
    refetchInterval: 3000,
  });

  useEffect(() => {
    if (diagnostics?.udisk_drives && diagnostics.udisk_drives.length > 0 && !selectedUDisk) {
      setSelectedUDisk(diagnostics.udisk_drives[0].drive_letter);
    }
  }, [diagnostics, selectedUDisk]);

  const targetDriveLetter = selectedUDisk || diagnostics?.udisk_drives?.[0]?.drive_letter || "";

  const {
    data: udiskPreview,
    isLoading: isPreviewLoading,
    refetch: refetchUDiskPreview,
  } = useQuery({
    queryKey: ["udisk-preview", targetDriveLetter],
    queryFn: () =>
      apiFetch<UDiskPreview>(`/devices/udisk/preview?drive_letter=${encodeURIComponent(targetDriveLetter)}`, {}, token),
    enabled: !!token && !!targetDriveLetter && (diagnostics?.primary_mode === "UDISK" || (diagnostics?.udisk_drives?.length ?? 0) > 0),
  });

  function formatBytes(bytes: number): string {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  }

  async function handleExtractUDisk(targetDrive?: string) {
    const drive = targetDrive || selectedUDisk || (diagnostics?.udisk_drives?.[0]?.drive_letter);
    if (!drive) {
      setError("Please select a valid U-Disk phone storage drive.");
      return;
    }
    if (activeCategoryList.length === 0) {
      setError("Please select at least one category to extract.");
      return;
    }
    setError(null);
    setMsg(null);
    setBusy(true);
    try {
      const caseId = await ensureCaseId();
      const res = await apiFetch<{
        status: string;
        acquisition_id: number;
        acquisition_uid: string;
        categories_extracted: string[];
      }>(
        "/devices/udisk/extract",
        {
          method: "POST",
          body: JSON.stringify({
            case_id: caseId,
            drive_letter: drive,
            categories: activeCategoryList,
          }),
        },
        token
      );

      setActiveAcquisitionId(res.acquisition_id);
      setExtractedAcqId(res.acquisition_id);

      // Fetch extracted records directly
      const callsRes = await apiFetch<{ items: ExtractedCall[] }>(
        `/acquisitions/${res.acquisition_id}/calls?limit=200`,
        {},
        token
      );
      const smsRes = await apiFetch<{ items: ExtractedSms[] }>(
        `/acquisitions/${res.acquisition_id}/sms?limit=200`,
        {},
        token
      );
      setExtractedCalls(callsRes.items || []);
      setExtractedMessages(smsRes.items || []);

      const carvedSmsCount = (smsRes.items || []).filter((s) => s.status === "DELETED_RECOVERED").length;
      const carvedCallsCount = (callsRes.items || []).filter((c) => c.storage_location?.includes("CARVED")).length;

      setMsg(
        `U-Disk Forensic Extraction completed successfully from ${drive}! Acquired ${callsRes.items?.length || 0} call logs (${carvedCallsCount} carved/deleted) and ${smsRes.items?.length || 0} SMS messages (${carvedSmsCount} carved/deleted) with SHA-256 evidence vault integrity.`
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

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
        setError(
          res.error_detail ||
            `Port ${selectedPort} opened, but no response to AT commands. Ensure your feature phone is powered ON, unlocked, and set to 'COM Port / Modem / PC Suite' mode.`
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
    if (activeCategoryList.length === 0) {
      setError("Please select at least one category to extract.");
      return;
    }
    setMsg(null);
    setError(null);
    setBusy(true);
    try {
      const caseId = await ensureCaseId();
      let deviceId = ident?.device_id;

      if (!deviceId) {
        // Auto-probe and register device on the active port
        const idRes = await apiFetch<IdentifyResult>(
          "/devices/identify",
          { method: "POST", body: JSON.stringify({ case_id: caseId }) },
          token
        );
        setIdent(idRes);
        deviceId = idRes.device_id;
        if (!deviceId) {
          throw new Error(
            idRes.error_detail ||
              "Cannot extract: Handset did not respond with 'OK' to AT commands on this port. Ensure phone is ON and in 'COM Port / Modem / PC Suite' mode."
          );
        }
        setActiveDeviceId(deviceId);
      }

      const acq = await apiFetch<AcquisitionOut>(
        "/acquisitions",
        {
          method: "POST",
          body: JSON.stringify({
            case_id: caseId,
            device_id: deviceId,
            categories: activeCategoryList,
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

      {/* USB Connection Mode Hub */}
      {diagnostics?.primary_mode === "UDISK" || (diagnostics?.udisk_drives && diagnostics.udisk_drives.length > 0) ? (
        <div className="rounded-xl border border-emerald-500/50 bg-emerald-950/40 p-5 text-emerald-200 shadow-xl shadow-emerald-950/50 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-emerald-800/60 pb-3">
            <div className="flex items-center gap-2 font-semibold text-emerald-300 text-base">
              <HardDrive className="h-5 w-5 text-emerald-400 shrink-0" />
              <span>Pre-Extraction Forensic Reconnaissance & Artifact Preview — U Disk Mode</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-emerald-500/20 border border-emerald-400/40 px-3 py-1 text-xs font-semibold text-emerald-300 uppercase tracking-wide">
                Storage Analyzed & Ready
              </span>
              <button
                onClick={() => refetchUDiskPreview()}
                disabled={isPreviewLoading}
                title="Re-scan phone storage"
                className="rounded bg-emerald-900/60 border border-emerald-700/50 p-1.5 text-emerald-300 hover:bg-emerald-800 transition"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isPreviewLoading ? "animate-spin" : ""}`} />
              </button>
            </div>
          </div>

          {/* Drive & Capacity Overview */}
          <div className="rounded-lg bg-slate-900/90 border border-slate-800 p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="text-xs text-slate-400 block">Phone Storage Volume:</span>
                <div className="flex items-center gap-2 mt-0.5">
                  {diagnostics.udisk_drives && diagnostics.udisk_drives.length > 1 ? (
                    <select
                      value={selectedUDisk}
                      onChange={(e) => setSelectedUDisk(e.target.value)}
                      className="rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-sm font-semibold text-emerald-400"
                    >
                      {diagnostics.udisk_drives.map((d) => (
                        <option key={d.drive_letter} value={d.drive_letter}>
                          {d.drive_letter} ({d.volume_name || "REMOVABLE"}) — {d.phone_vendor || "Feature Phone"}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <span className="font-mono text-sm font-semibold text-emerald-400">
                      {targetDriveLetter} ({udiskPreview?.phone_vendor || diagnostics.udisk_drives?.[0]?.phone_vendor || "Feature Phone Storage"})
                    </span>
                  )}
                  <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                    FS: {udiskPreview?.filesystem || diagnostics.udisk_drives?.[0]?.filesystem || "FAT"}
                  </span>
                  <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-[11px] text-slate-300">
                    Label: {udiskPreview?.volume_name || diagnostics.udisk_drives?.[0]?.volume_name || "REMOVABLE"}
                  </span>
                </div>
              </div>

              {/* Disk Capacity Bar */}
              {udiskPreview && udiskPreview.total_bytes > 0 && (
                <div className="w-full sm:w-64 text-xs space-y-1">
                  <div className="flex justify-between text-slate-400">
                    <span>Used: {formatBytes(udiskPreview.used_bytes)}</span>
                    <span>Total: {formatBytes(udiskPreview.total_bytes)}</span>
                  </div>
                  <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                    <div
                      className="h-full bg-emerald-500 rounded-full"
                      style={{
                        width: `${Math.min(100, Math.round((udiskPreview.used_bytes / udiskPreview.total_bytes) * 100))}%`,
                      }}
                    />
                  </div>
                  <span className="text-[11px] text-slate-500 block text-right">
                    {formatBytes(udiskPreview.free_bytes)} free
                  </span>
                </div>
              )}
            </div>

            {/* 4 Feature & Artifact Preview Metric Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2">
              <div className="rounded-lg bg-slate-950/80 border border-slate-800/80 p-3 space-y-1">
                <div className="flex items-center gap-1.5 text-xs text-sky-400 font-medium">
                  <Smartphone className="h-4 w-4" />
                  <span>Contacts</span>
                </div>
                <div className="text-xl font-bold font-mono text-slate-100">
                  {isPreviewLoading ? "..." : udiskPreview?.contacts_count ?? 0}
                </div>
                <p className="text-[11px] text-slate-400">
                  vCard (.vcf) entries detected
                </p>
              </div>

              <div className="rounded-lg bg-slate-950/80 border border-slate-800/80 p-3 space-y-1">
                <div className="flex items-center gap-1.5 text-xs text-indigo-400 font-medium">
                  <MessageSquare className="h-4 w-4" />
                  <span>SMS Messages</span>
                </div>
                <div className="text-xl font-bold font-mono text-slate-100">
                  {isPreviewLoading ? "..." : udiskPreview?.sms_count ?? 0}
                </div>
                <p className="text-[11px] text-slate-400">
                  vMessage (.vmg) records found
                </p>
              </div>

              <div className="rounded-lg bg-slate-950/80 border border-slate-800/80 p-3 space-y-1">
                <div className="flex items-center gap-1.5 text-xs text-emerald-400 font-medium">
                  <PhoneCall className="h-4 w-4" />
                  <span>Call History</span>
                </div>
                <div className="text-xl font-bold font-mono text-slate-100">
                  {isPreviewLoading ? "..." : udiskPreview?.calls_count ?? 0}
                </div>
                <p className="text-[11px] text-slate-400">
                  Dialed, received & missed logs
                </p>
              </div>

              <div className="rounded-lg bg-slate-950/80 border border-purple-900/50 bg-purple-950/20 p-3 space-y-1">
                <div className="flex items-center gap-1.5 text-xs text-purple-300 font-medium">
                  <Binary className="h-4 w-4" />
                  <span>Carving Targets</span>
                </div>
                <div className="text-xl font-bold font-mono text-purple-200">
                  {isPreviewLoading ? "..." : udiskPreview?.carved_candidates_count ?? 0}
                </div>
                <p className="text-[11px] text-purple-300/80">
                  Binary files eligible for deleted carving
                </p>
              </div>
            </div>

            {/* Discovered Artifact Files Explorer */}
            {udiskPreview?.artifacts && udiskPreview.artifacts.length > 0 && (
              <div className="space-y-1.5 pt-2 border-t border-slate-800">
                <div className="flex items-center justify-between text-xs text-slate-300">
                  <span className="font-semibold flex items-center gap-1.5">
                    <FileSearch className="h-3.5 w-3.5 text-emerald-400" />
                    Discovered Forensic Artifact Files ({udiskPreview.artifacts.length}):
                  </span>
                  <span className="text-[11px] text-slate-500">
                    Preview of candidate files analyzed before extraction
                  </span>
                </div>

                <div className="max-h-48 overflow-y-auto rounded border border-slate-800 bg-slate-950 divide-y divide-slate-900">
                  {udiskPreview.artifacts.map((art, idx) => (
                    <div key={idx} className="flex items-center justify-between px-3 py-2 text-xs hover:bg-slate-900/50">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-mono text-slate-200 truncate">{art.file_name}</span>
                        <span className="text-[11px] text-slate-500 font-mono truncate max-w-xs">({art.file_path})</span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-slate-400 font-mono text-[11px]">{formatBytes(art.size_bytes)}</span>
                        <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[11px] font-mono text-slate-300 uppercase">
                          {art.category}
                        </span>
                        {art.is_deleted_carvable && (
                          <span className="rounded bg-purple-950 border border-purple-800 px-1.5 py-0.5 text-[10px] font-semibold text-purple-300">
                            🛡️ Carvable Deleted
                          </span>
                        )}
                        <span className="font-semibold text-emerald-400 text-[11px]">
                          ~{art.estimated_count} records
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Category Selection Checklist */}
            <div className="space-y-2 pt-2 border-t border-slate-800">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <ListChecks className="h-4 w-4 text-emerald-400" />
                  Select Forensic Categories to Acquire:
                </span>
                <div className="flex gap-2 text-xs">
                  <button
                    onClick={selectAllCategories}
                    className="text-emerald-400 hover:text-emerald-300 underline text-[11px]"
                  >
                    Select All
                  </button>
                  <span className="text-slate-600">|</span>
                  <button
                    onClick={deselectAllCategories}
                    className="text-slate-400 hover:text-slate-300 underline text-[11px]"
                  >
                    Clear All
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[
                  { key: "device_info" as const, label: "Device Info", desc: "Volume & serial specs" },
                  { key: "contacts" as const, label: "Contacts", desc: "vCard address books" },
                  { key: "sms" as const, label: "SMS Messages", desc: "vMessage & carved PDUs" },
                  { key: "call_history" as const, label: "Call History", desc: "Logs & carved records" },
                ].map((item) => (
                  <label
                    key={item.key}
                    onClick={() => toggleCategory(item.key)}
                    className={`flex items-start gap-2 rounded-lg border p-2.5 cursor-pointer transition ${
                      selectedCategories[item.key]
                        ? "border-emerald-600/70 bg-emerald-950/30 text-emerald-200"
                        : "border-slate-800 bg-slate-950/50 text-slate-400 hover:border-slate-700"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedCategories[item.key]}
                      onChange={() => {}} // handled by parent onClick
                      className="mt-0.5 rounded border-slate-700 bg-slate-900 text-emerald-600 focus:ring-0"
                    />
                    <div>
                      <span className="text-xs font-semibold block">{item.label}</span>
                      <span className="text-[10px] text-slate-400">{item.desc}</span>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* Forensic Acquisition Action Button & Guarantee */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-800">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <ShieldCheck className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>
                  <strong>Forensic Guarantee:</strong> 100% Read-Only acquisition. All extracted files secured with SHA-256 evidence hashes.
                </span>
              </div>

              <button
                onClick={() => handleExtractUDisk(targetDriveLetter)}
                disabled={busy || activeCategoryList.length === 0}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-emerald-500 shadow-lg shadow-emerald-900/40 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <FolderTree className="h-4 w-4" />
                {busy ? "Extracting Selected Categories..." : `Proceed with Extraction (${activeCategoryList.length} Selected)`}
              </button>
            </div>
          </div>
        </div>
      ) : diagnostics?.primary_mode === "COM_DRIVER_MISSING" || (diagnostics?.driver_problem_devices && diagnostics.driver_problem_devices.length > 0) ? (
        <div className="rounded-xl border border-amber-500/50 bg-amber-950/40 p-5 text-amber-200 shadow-xl shadow-amber-950/50 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 font-semibold text-amber-300 text-sm">
              <Cpu className="h-5 w-5 text-amber-400 shrink-0" />
              <span>COM Mode Detected — Windows USB Serial Driver Not Bound (Code 28)</span>
            </div>
            <span className="rounded-full bg-amber-500/20 border border-amber-400/40 px-2.5 py-0.5 text-xs font-semibold text-amber-300">
              Hardware Connected: {diagnostics.driver_problem_devices?.[0]?.vendor || "MediaTek"}
            </span>
          </div>

          <p className="text-slate-200 text-xs leading-relaxed">
            A real <strong>{diagnostics.driver_problem_devices?.[0]?.vendor || "MediaTek / Spreadtrum"}</strong> handset is physically connected in COM/Modem mode (<code>{diagnostics.driver_problem_devices?.[0]?.hardware_id || "USB\\VID_0E8D&PID_0003"}</code>). Because Windows doesn't bind a default serial driver for this hardware ID, it does not have a COM port assigned yet.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
            <div className="rounded-lg bg-slate-900/90 border border-emerald-800/60 p-3.5 space-y-2 text-xs">
              <span className="font-semibold text-emerald-300 block flex items-center gap-1.5">
                ⚡ Option 1: Automated 1-Click Driver Fix (Recommended)
              </span>
              <p className="text-slate-300 text-xs">
                We generated an automated driver installer script in your project root:
              </p>
              <div className="rounded bg-slate-950 p-2 font-mono text-emerald-400 text-xs border border-slate-800 select-all">
                D:\FeaturePhone\Install_Phone_Drivers.bat
              </div>
              <p className="text-[11px] text-slate-400">
                Double-click <strong>Install_Phone_Drivers.bat</strong> on your computer (or right-click &rarr; <em>Run as administrator</em>). It installs the certified VCOM INF driver package and assigns a COM port instantly.
              </p>
            </div>

            <div className="rounded-lg bg-slate-900/90 border border-slate-800 p-3.5 space-y-2 text-xs">
              <span className="font-semibold text-amber-300 block">
                🛠️ Option 2: Manual Device Manager Binding (30 Seconds)
              </span>
              <ol className="list-decimal list-inside space-y-1 text-slate-300 text-[11px]">
                <li>Press <strong>Win + X</strong> and open <strong>Device Manager</strong> (or run <code>devmgmt.msc</code>).</li>
                <li>Under <strong>Other devices</strong>, right-click the warning item (<code>{diagnostics.driver_problem_devices?.[0]?.hardware_id || "USB\\VID_0E8D&PID_0003"}</code>).</li>
                <li>Click <strong>Update driver &rarr; Browse my computer &rarr; Let me pick from a list</strong>.</li>
                <li>Select <strong>Ports (COM & LPT)</strong> &rarr; Manufacturer: <strong>(Standard port types)</strong> &rarr; Model: <strong>USB Serial Device</strong>.</li>
                <li>Click Next. Windows binds <code>usbser.sys</code> and assigns a COM port immediately.</li>
              </ol>
            </div>
          </div>

          <div className="rounded-lg bg-slate-900/80 border border-slate-800 p-2.5 text-xs text-slate-400 flex items-center justify-between">
            <span>
              💡 <strong>Prefer U-Disk Storage Mode without drivers?</strong> Unplug the USB cable, plug it back in, and select <strong>"U Disk" / "Mass Storage"</strong> on the phone screen.
            </span>
          </div>
        </div>
      ) : diagnostics?.primary_mode === "CHARGING_ONLY" ? (
        <div className="rounded-xl border border-sky-500/50 bg-sky-950/40 p-5 text-xs text-sky-200 shadow-xl shadow-sky-950/50 space-y-3">
          <div className="flex items-center gap-2 font-semibold text-sky-300 text-sm">
            <Smartphone className="h-5 w-5 text-sky-400 shrink-0" />
            <span>Phone Connected in Charging-Only Mode</span>
          </div>
          <p className="text-slate-200 leading-relaxed">
            The phone is drawing power, but USB data lines are inactive. To extract data:
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
            <div className="rounded-lg bg-slate-900/90 p-3 border border-slate-800">
              <span className="font-semibold text-emerald-400 block mb-1">To Extract via U-Disk Mode:</span>
              <p className="text-slate-300 text-xs">
                Unplug and re-plug the cable. When the phone screen lights up with options, press the OK/center key to select <strong>"U Disk" / "Storage"</strong>.
              </p>
            </div>
            <div className="rounded-lg bg-slate-900/90 p-3 border border-slate-800">
              <span className="font-semibold text-cyan-400 block mb-1">To Extract via COM Port Mode:</span>
              <p className="text-slate-300 text-xs">
                In phone menu, go to <strong>Settings &rarr; Phone Settings &rarr; UART / USB Mode</strong> and choose <strong>"COM Port" / "Modem"</strong>.
              </p>
            </div>
          </div>
        </div>
      ) : !hasUsbPhoneDetected && !isSimulatorPort && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 text-xs text-amber-200">
          <div className="flex items-center gap-2 font-semibold text-amber-300 text-sm mb-1">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            No Real USB Feature Phone Detected
          </div>
          <p>
            Please connect your feature phone (Nokia, Tecno, Itel, Samsung, etc.) using a <strong>USB data cable</strong> and select <strong>"U Disk"</strong> or <strong>"COM Port / Modem"</strong> on the phone screen.
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
                    : "[SERIAL PORT]";
                return (
                  <option key={p.port_name} value={p.port_name}>
                    {badge} {p.description}
                  </option>
                );
              })}
              {ports.length === 0 && <option value="">No COM ports detected</option>}
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

          <div className="flex flex-wrap items-center gap-2 pt-2">
            {!status?.connected ? (
              <button
                onClick={handleConnectAndVerify}
                disabled={busy || !selectedPort}
                title="Connect to serial port and verify AT handshake"
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

            {/* Extraction button: active when connected */}
            <button
              onClick={handleExtractCallsAndMessages}
              disabled={busy || !status?.connected}
              title={
                !status?.connected
                  ? "Connect a serial port first"
                  : "Extract phone calls and SMS messages"
              }
              className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition ${status?.connected && !busy
                ? "bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-900/40"
                : "bg-slate-800 text-slate-500 cursor-not-allowed opacity-50"
                }`}
            >
              <PhoneCall className="h-4 w-4" />
              {busy
                ? "Extracting..."
                : status?.connected
                  ? phoneDisplayName ? `Extract Calls & Messages (${phoneDisplayName})` : "Extract Calls & Messages"
                  : "Extract Calls & Messages (Connect Port First)"}
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

      {/* Pre-Extraction Feature & Storage Slot Preview for COM Mode */}
      {isDeviceActiveAndReady && (
        <div className="rounded-xl border border-cyan-500/50 bg-cyan-950/30 p-6 text-slate-200 shadow-xl shadow-cyan-950/40 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-cyan-800/60 pb-3">
            <div>
              <h3 className="text-base font-semibold text-cyan-200 flex items-center gap-2">
                <Eye className="h-5 w-5 text-cyan-400" />
                3. Pre-Extraction Feature & Storage Slot Reconnaissance — {phoneDisplayName}
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Probed storage slot occupancy and AT capabilities before initiating forensic extraction
              </p>
            </div>
            <span className="rounded-full bg-cyan-500/20 border border-cyan-400/40 px-3 py-1 text-xs font-semibold text-cyan-300 uppercase tracking-wide">
              AT Responsive & Verified
            </span>
          </div>

          {/* Storage Slot Occupancy Matrix */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Call History Slots */}
            <div className="rounded-lg bg-slate-900/90 border border-slate-800 p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-emerald-400 flex items-center gap-1.5">
                  <PhoneCall className="h-4 w-4" /> Call History Registers
                </span>
                <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                  AT+CPBS
                </span>
              </div>
              <div className="space-y-1 text-xs font-mono">
                <div className="flex justify-between py-0.5 border-b border-slate-800/50">
                  <span className="text-slate-400">Missed Calls (MC):</span>
                  <span className="text-emerald-300 font-semibold">
                    {ident?.storage_stats?.calls?.MC
                      ? `${ident.storage_stats.calls.MC.used} / ${ident.storage_stats.calls.MC.total} used`
                      : "Supported / Available"}
                  </span>
                </div>
                <div className="flex justify-between py-0.5 border-b border-slate-800/50">
                  <span className="text-slate-400">Received Calls (RC):</span>
                  <span className="text-emerald-300 font-semibold">
                    {ident?.storage_stats?.calls?.RC
                      ? `${ident.storage_stats.calls.RC.used} / ${ident.storage_stats.calls.RC.total} used`
                      : "Supported / Available"}
                  </span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span className="text-slate-400">Dialed Calls (DC):</span>
                  <span className="text-emerald-300 font-semibold">
                    {ident?.storage_stats?.calls?.DC
                      ? `${ident.storage_stats.calls.DC.used} / ${ident.storage_stats.calls.DC.total} used`
                      : "Supported / Available"}
                  </span>
                </div>
              </div>
              <span className="text-[10px] text-slate-500 block pt-1">
                Source: Handset NVRAM log memory (not CDRs)
              </span>
            </div>

            {/* Contacts Slots */}
            <div className="rounded-lg bg-slate-900/90 border border-slate-800 p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-sky-400 flex items-center gap-1.5">
                  <Smartphone className="h-4 w-4" /> Phonebook Storage
                </span>
                <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                  AT+CPBS
                </span>
              </div>
              <div className="space-y-1 text-xs font-mono">
                <div className="flex justify-between py-0.5 border-b border-slate-800/50">
                  <span className="text-slate-400">SIM Storage (SM):</span>
                  <span className="text-sky-300 font-semibold">
                    {ident?.storage_stats?.contacts?.SM
                      ? `${ident.storage_stats.contacts.SM.used} / ${ident.storage_stats.contacts.SM.total} used`
                      : "Available on SIM"}
                  </span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span className="text-slate-400">Handset Storage (ME):</span>
                  <span className="text-sky-300 font-semibold">
                    {ident?.storage_stats?.contacts?.ME
                      ? `${ident.storage_stats.contacts.ME.used} / ${ident.storage_stats.contacts.ME.total} used`
                      : "Available on Phone"}
                  </span>
                </div>
              </div>
              <span className="text-[10px] text-slate-500 block pt-1">
                Protocol: AT+CPBR indexed sequential parsing
              </span>
            </div>

            {/* SMS Message Slots */}
            <div className="rounded-lg bg-slate-900/90 border border-slate-800 p-3.5 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-indigo-400 flex items-center gap-1.5">
                  <MessageSquare className="h-4 w-4" /> SMS Message Store
                </span>
                <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300">
                  AT+CPMS
                </span>
              </div>
              <div className="space-y-1 text-xs font-mono">
                <div className="flex justify-between py-0.5 border-b border-slate-800/50">
                  <span className="text-slate-400">SIM Storage (SM):</span>
                  <span className="text-indigo-300 font-semibold">
                    {ident?.storage_stats?.sms?.SM
                      ? `${ident.storage_stats.sms.SM.used} / ${ident.storage_stats.sms.SM.total} used`
                      : "Available on SIM"}
                  </span>
                </div>
                <div className="flex justify-between py-0.5">
                  <span className="text-slate-400">Handset Storage (ME):</span>
                  <span className="text-indigo-300 font-semibold">
                    {ident?.storage_stats?.sms?.ME
                      ? `${ident.storage_stats.sms.ME.used} / ${ident.storage_stats.sms.ME.total} used`
                      : "Available on Phone"}
                  </span>
                </div>
              </div>
              <span className="text-[10px] text-purple-300/80 block pt-1 font-sans">
                🛡️ PDU Mode (GSM 03.40) + Deleted Carving Active
              </span>
            </div>
          </div>

          {/* Category Selection Checklist */}
          <div className="rounded-lg bg-slate-900/90 border border-slate-800 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                <ListChecks className="h-4 w-4 text-cyan-400" />
                Select Forensic Categories to Acquire:
              </span>
              <div className="flex gap-2 text-xs">
                <button
                  onClick={selectAllCategories}
                  className="text-cyan-400 hover:text-cyan-300 underline text-[11px]"
                >
                  Select All
                </button>
                <span className="text-slate-600">|</span>
                <button
                  onClick={deselectAllCategories}
                  className="text-slate-400 hover:text-slate-300 underline text-[11px]"
                >
                  Clear All
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {[
                { key: "device_info" as const, label: "Device Info", desc: `IMEI: ${ident?.imei || "Available"}` },
                { key: "contacts" as const, label: "Contacts", desc: "SIM & Phonebook slots" },
                { key: "sms" as const, label: "SMS Messages", desc: "PDU hex & deleted carving" },
                { key: "call_history" as const, label: "Call History", desc: "Missed, received & dialed" },
              ].map((item) => (
                <label
                  key={item.key}
                  onClick={() => toggleCategory(item.key)}
                  className={`flex items-start gap-2 rounded-lg border p-2.5 cursor-pointer transition ${
                    selectedCategories[item.key]
                      ? "border-cyan-600/70 bg-cyan-950/40 text-cyan-200"
                      : "border-slate-800 bg-slate-950/50 text-slate-400 hover:border-slate-700"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedCategories[item.key]}
                    onChange={() => {}} // handled by parent onClick
                    className="mt-0.5 rounded border-slate-700 bg-slate-900 text-cyan-600 focus:ring-0"
                  />
                  <div>
                    <span className="text-xs font-semibold block">{item.label}</span>
                    <span className="text-[10px] text-slate-400">{item.desc}</span>
                  </div>
                </label>
              ))}
            </div>

            {/* Action Button & Non-destructive Notice */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-800">
              <div className="flex items-center gap-2 text-xs text-slate-400">
                <ShieldCheck className="h-4 w-4 text-cyan-400 shrink-0" />
                <span>
                  <strong>Non-Destructive AT Execution:</strong> Commands are strictly read-only. Destructive resets (AT+CMGD, AT+CPBW) are hard-blocked.
                </span>
              </div>

              <button
                onClick={handleExtractCallsAndMessages}
                disabled={busy || activeCategoryList.length === 0}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 shadow-lg shadow-indigo-900/40 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <PhoneCall className="h-4 w-4" />
                {busy ? "Extracting..." : `Proceed with Forensic Extraction (${activeCategoryList.length} Selected)`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Extracted Phone Calls & Messages Display with Format Downloads */}
      {extractedAcqId && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
            <div>
              <h3 className="text-lg font-semibold text-slate-100 flex items-center gap-2">
                <Smartphone className="h-5 w-5 text-indigo-400" />
                4. Extracted Evidence Records — {phoneDisplayName || "Acquisition"} (#{extractedAcqId})
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
                        <td className="py-2 px-3 font-mono text-slate-400">
                          {c.storage_location?.includes("CARVED") ? (
                            <span className="inline-flex items-center gap-1 rounded bg-purple-950 border border-purple-800 px-1.5 py-0.5 text-[11px] font-semibold text-purple-300">
                              🛡️ CARVED DELETED
                            </span>
                          ) : (
                            c.storage_location
                          )}
                        </td>
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

                    const isDeleted = m.status === "DELETED_RECOVERED";

                    return (
                      <tr key={i} className="hover:bg-slate-900/40">
                        <td className="py-2 px-3 font-mono text-slate-400">{m.storage_location}</td>
                        <td className="py-2 px-3 font-medium">
                          {isDeleted ? (
                            <span className="inline-flex items-center gap-1 rounded bg-purple-950 border border-purple-800 px-2 py-0.5 text-[11px] font-semibold text-purple-300">
                              🛡️ DELETED (RECOVERED)
                            </span>
                          ) : (
                            <span className="text-sky-300">{m.status || "Unavailable"}</span>
                          )}
                        </td>
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
