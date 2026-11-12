import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, CheckCircle2, FolderKanban, Smartphone } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiFetch } from "../lib/api";
import { useLabStore } from "../store/useAuthStore";

interface DashboardSummary {
  total_cases: number;
  connected_devices: number;
  completed_acquisitions: number;
  failed_acquisitions: number;
  recent_activities: Array<{
    id: number;
    action: string;
    case_id: number | null;
    acquisition_id: number | null;
    created_at: string;
  }>;
}

export function DashboardPage() {
  const token = useLabStore((s) => s.token);
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => apiFetch<DashboardSummary>("/dashboard/summary", {}, token),
    enabled: !!token,
  });

  if (isLoading || !data) {
    return <div className="text-slate-400">Loading forensic laboratory metrics...</div>;
  }

  const chartData = [
    { name: "Cases", value: data.total_cases },
    { name: "Connected", value: data.connected_devices },
    { name: "Completed Acq.", value: data.completed_acquisitions },
    { name: "Failed Acq.", value: data.failed_acquisitions },
  ];

  const cards = [
    { label: "Total Examination Cases", value: data.total_cases, icon: FolderKanban, tone: "text-sky-400" },
    { label: "Connected Devices", value: data.connected_devices, icon: Smartphone, tone: "text-emerald-400" },
    { label: "Completed Acquisitions", value: data.completed_acquisitions, icon: CheckCircle2, tone: "text-teal-400" },
    { label: "Failed Acquisitions", value: data.failed_acquisitions, icon: AlertTriangle, tone: "text-rose-400" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-slate-100">Forensic Laboratory Dashboard</h2>
        <p className="text-sm text-slate-400">Offline logical extraction & evidence integrity overview</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((c) => {
          const Icon = c.icon;
          return (
            <div key={c.label} className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium uppercase tracking-wider text-slate-400">{c.label}</span>
                <Icon className={`h-5 w-5 ${c.tone}`} />
              </div>
              <p className="mt-3 text-3xl font-bold text-slate-100">{c.value}</p>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-300">Acquisition Overview</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} />
                <Tooltip contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155" }} />
                <Bar dataKey="value" fill="#38bdf8" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="mb-4 flex items-center gap-2">
            <Activity className="h-4 w-4 text-sky-400" />
            <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">Recent Audit Activities</h3>
          </div>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {data.recent_activities.map((a) => (
              <div key={a.id} className="flex items-center justify-between rounded-lg bg-slate-950/60 px-3 py-2 text-xs">
                <span className="font-mono font-semibold text-sky-300">{a.action}</span>
                <span className="text-slate-400">{new Date(a.created_at).toLocaleString()}</span>
              </div>
            ))}
            {data.recent_activities.length === 0 && (
              <p className="text-sm text-slate-500">No audit events recorded yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
