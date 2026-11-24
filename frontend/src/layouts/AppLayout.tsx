import { BarChart3, Database, History, Layers, Menu, Search, Settings, X } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { StatusDot } from "../components/ui";
import { api } from "../services/api";
import { useAsync } from "../hooks/useAsync";
import { cn } from "../utils/format";

const NAV = [
  { to: "/", label: "New Query", icon: Search, end: true },
  { to: "/history", label: "Query History", icon: History },
  { to: "/explorer", label: "Database Explorer", icon: Database },
  { to: "/schema", label: "Schema Management", icon: Layers },
  { to: "/evaluation", label: "Evaluation", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

function HealthIndicator() {
  const { data, error } = useAsync(() => api.health(), [], 30000);
  const status = error ? "down" : (data?.status ?? "unknown");
  const label = error ? "Backend unreachable" : data ? `Backend ${data.status}` : "Checking backend";
  return (
    <div className="flex items-center gap-2 text-xs text-slate-400" title={data ? Object.entries(data.components).map(([k, v]) => `${k}: ${v.status}`).join(", ") : undefined}>
      <StatusDot status={status} />
      {label}
    </div>
  );
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-1 px-3">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white",
            )
          }
        >
          <Icon className="h-4 w-4" aria-hidden />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2 px-6 py-5">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">Q</div>
      <div>
        <p className="text-sm font-semibold text-white">QueryMind AI</p>
        <p className="text-[11px] text-slate-400">Schema-aware SQL</p>
      </div>
    </div>
  );
}

export function AppLayout() {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 flex-col bg-slate-900 lg:flex">
        <Brand />
        <div className="flex-1 overflow-y-auto">
          <Nav />
        </div>
        <div className="px-6 py-4">
          <HealthIndicator />
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setOpen(false)} />
          <aside className="relative flex h-full w-64 flex-col bg-slate-900">
            <button type="button" aria-label="Close navigation" className="absolute right-3 top-4 text-slate-300" onClick={() => setOpen(false)}>
              <X className="h-5 w-5" />
            </button>
            <Brand />
            <div className="flex-1 overflow-y-auto">
              <Nav onNavigate={() => setOpen(false)} />
            </div>
            <div className="px-6 py-4">
              <HealthIndicator />
            </div>
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
          <button type="button" aria-label="Open navigation" onClick={() => setOpen(true)} className="rounded-md p-1 text-slate-600 hover:bg-slate-100">
            <Menu className="h-5 w-5" />
          </button>
          <span className="text-sm font-semibold">QueryMind AI</span>
        </header>
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-6xl px-4 py-6 sm:px-8 sm:py-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
