import { FormEvent, useState } from "react";
import { ClipboardList, FileBarChart2, FolderPlus, LayoutDashboard, LogOut, PlayCircle, Search, Shield, Smartphone } from "lucide-react";
import { apiFetch } from "./lib/api";
import { AcquisitionPage } from "./pages/AcquisitionPage";
import { AuditAdminPage } from "./pages/AuditAdminPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DeviceConnectionPage } from "./pages/DeviceConnectionPage";
import { NewExaminationPage } from "./pages/NewExaminationPage";
import { ReportsPage } from "./pages/ReportsPage";
import { ResultsPage } from "./pages/ResultsPage";
import { ExaminerProfile, useLabStore } from "./store/useAuthStore";

type Page = "dashboard" | "devices" | "cases" | "acquisition" | "results" | "reports" | "audit";

export default function App() {
  const { token, examiner, setAuth, logout } = useLabStore();
  const [page, setPage] = useState<Page>("dashboard");
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("ForensicsLab!2026");
  const [loginError, setLoginError] = useState<string | null>(null);

  async function handleLogin(e: FormEvent) {
    e.preventDefault();
    setLoginError(null);
    try {
      const res = await apiFetch<{ access_token: string; examiner: ExaminerProfile }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      setAuth(res.access_token, res.examiner);
    } catch (err) {
      setLoginError((err as Error).message);
    }
  }

  if (!token || !examiner) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 p-4">
        <form onSubmit={handleLogin} className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 space-y-5">
          <div className="flex items-center gap-3">
            <Shield className="h-8 w-8 text-sky-400" />
            <div>
              <h1 className="text-lg font-bold text-slate-100">Feature Phone Forensics</h1>
              <p className="text-xs text-slate-400">Offline Digital Evidence Extraction Lab</p>
            </div>
          </div>
          {loginError && <div className="rounded border border-rose-800 bg-rose-950/60 px-3 py-2 text-xs text-rose-200">{loginError}</div>}
          <div>
            <label className="block text-xs text-slate-400 mb-1">Examiner Username</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Password</label>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm" />
          </div>
          <button type="submit" className="w-full rounded-lg bg-sky-600 py-2.5 text-sm font-semibold hover:bg-sky-500">
            Sign In to Laboratory
          </button>
        </form>
      </div>
    );
  }

  const nav: Array<[Page, string, typeof LayoutDashboard]> = [
    ["dashboard", "Dashboard", LayoutDashboard],
    ["devices", "Device Connection", Smartphone],
    ["cases", "New Examination", FolderPlus],
    ["acquisition", "Acquisition", PlayCircle],
    ["results", "Examination Results", Search],
    ["reports", "Reports & Hashes", FileBarChart2],
    ["audit", "Audit & Admin", ClipboardList],
  ];

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      <aside className="w-64 border-r border-slate-800 bg-slate-900/70 p-4 flex flex-col">
        <div className="flex items-center gap-2.5 px-2 pb-6 border-b border-slate-800">
          <Shield className="h-6 w-6 text-sky-400" />
          <div>
            <p className="text-sm font-bold leading-tight">FP Forensics</p>
            <p className="text-[11px] text-slate-400">Offline Lab v0.1</p>
          </div>
        </div>
        <nav className="mt-4 flex-1 space-y-1">
          {nav.map(([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setPage(id)}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
                page === id ? "bg-sky-600 text-white font-medium" : "text-slate-300 hover:bg-slate-800"
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </nav>
        <div className="border-t border-slate-800 pt-3 text-xs text-slate-400 flex items-center justify-between">
          <div>
            <p className="font-medium text-slate-200">{examiner.full_name}</p>
            <p className="uppercase">{examiner.role}</p>
          </div>
          <button onClick={logout} title="Sign out" className="rounded p-1.5 hover:bg-slate-800 text-slate-300">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </aside>

      <main className="flex-1 p-6 overflow-y-auto">
        {page === "dashboard" && <DashboardPage />}
        {page === "devices" && <DeviceConnectionPage onNavigateResults={() => setPage("results")} />}
        {page === "cases" && <NewExaminationPage />}
        {page === "acquisition" && <AcquisitionPage />}
        {page === "results" && <ResultsPage />}
        {page === "reports" && <ReportsPage />}
        {page === "audit" && <AuditAdminPage />}
      </main>
    </div>
  );
}

