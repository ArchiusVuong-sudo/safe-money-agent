import { FlaskConical, ListTree, RotateCcw, Smartphone } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";
import type { AppStateInfo } from "../lib/types";
import { Badge } from "./ui/badge";

export type Page = "demo" | "runs" | "evals";

export function TopBar({
  page,
  onPage,
  info,
  onReset,
  resetDisabled,
}: {
  page: Page;
  onPage: (p: Page) => void;
  info: AppStateInfo | null;
  onReset: () => void;
  resetDisabled: boolean;
}) {
  const tabs: { id: Page; label: string; icon: ReactNode }[] = [
    { id: "demo", label: "App", icon: <Smartphone className="size-4" /> },
    { id: "runs", label: "Runs", icon: <ListTree className="size-4" /> },
    { id: "evals", label: "Evals", icon: <FlaskConical className="size-4" /> },
  ];
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-8">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-brand-600 text-white">
            <svg viewBox="0 0 24 24" className="size-4.5" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div className="leading-tight">
            <div className="text-[14px] font-semibold">Safe Money Agent</div>
            <div className="text-[11px] text-slate-400">Prototype</div>
          </div>
        </div>
        <nav className="flex items-center gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              data-testid={`nav-${t.id}`}
              onClick={() => onPage(t.id)}
              className={cn(
                "flex h-9 items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium transition-colors",
                page === t.id ? "bg-slate-100 text-slate-900" : "text-slate-500 hover:bg-slate-50 hover:text-slate-800",
              )}
            >
              {t.icon}
              {t.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="warn" data-testid="synthetic-badge">
          Synthetic household - no real accounts or money
        </Badge>
        {info &&
          (info.mode === "replay" ? (
            <Badge variant="info" title={`Recorded live runs, played back (${info.mode_reason})`} data-testid="mode-badge">
              Replay mode
            </Badge>
          ) : (
            <Badge variant="good" title={info.mode_reason} data-testid="mode-badge">
              <span className="size-1.5 rounded-full bg-emerald-500" /> Live · {info.model}
            </Badge>
          ))}
        <button
          type="button"
          onClick={onReset}
          disabled={resetDisabled}
          className="ml-1 flex h-8 items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 text-[12px] font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          title="Reseed the synthetic household and clear the chat"
        >
          <RotateCcw className="size-3.5" /> Reset demo
        </button>
      </div>
    </header>
  );
}
