import { Home as HomeIcon, ListOrdered, MessageSquare } from "lucide-react";
import { useState } from "react";
import { ActivityScreen } from "../components/ActivityScreen";
import { AssistantScreen } from "../components/AssistantScreen";
import { HomeScreen } from "../components/HomeScreen";
import { TracePanel } from "../components/TracePanel";
import { cn } from "../lib/cn";
import type { Demo } from "../lib/useDemo";

type Screen = "home" | "assistant" | "activity";

export const FIX_PROMPT = "Checking is forecast to drop below $0 before payday. Fix this.";

export function DemoPage({ demo }: { demo: Demo }) {
  const [screen, setScreen] = useState<Screen>("home");
  const traceRun = demo.chat.find((r) => r.id === demo.traceRunId) ?? null;
  const live = demo.running && traceRun?.status === "running";
  const ask = (q: string) => {
    setScreen("assistant");
    void demo.send(q);
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-[440px_1fr] gap-6 px-6 py-5">
      <div className="flex min-h-0 justify-center">
        <div className="relative flex h-full max-h-[800px] w-[392px] flex-col overflow-hidden rounded-[44px] border-[10px] border-slate-900 bg-slate-50 shadow-2xl shadow-slate-900/20">
          <div className="flex h-9 shrink-0 items-center justify-between px-6 pt-1 text-[11px] font-semibold text-slate-700">
            <span>9:41</span>
            <span className="absolute left-1/2 top-2 h-5 w-24 -translate-x-1/2 rounded-full bg-slate-900" />
            <span className="rounded bg-amber-100 px-1.5 py-px text-[9.5px] font-semibold text-amber-800">SYNTHETIC</span>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">
            {screen === "home" && (
              <div className="scroll-thin h-full overflow-y-auto">
                {demo.home ? (
                  <HomeScreen home={demo.home} busy={demo.running} onFix={() => ask(FIX_PROMPT)} />
                ) : (
                  <Skeleton />
                )}
              </div>
            )}
            {screen === "assistant" && (
              <AssistantScreen
                chat={demo.chat}
                pendingMessage={demo.pendingMessage}
                running={demo.running}
                liveSteps={(demo.traceRunId && demo.steps[demo.traceRunId]) || []}
                suggestions={(demo.info?.suggestions ?? []).filter((q) => !demo.chat.some((r) => r.prompt === q))}
                error={demo.error}
                onSend={(m) => void demo.send(m)}
                onDecide={demo.decide}
                onSelectRun={demo.showTrace}
                selectedRunId={demo.traceRunId}
              />
            )}
            {screen === "activity" && (demo.txns ? <ActivityScreen txns={demo.txns} busy={demo.running} onAsk={ask} /> : <Skeleton />)}
          </div>
          <nav className="grid shrink-0 grid-cols-3 border-t border-slate-200 bg-white pb-3 pt-1.5">
            {(
              [
                ["home", "Home", HomeIcon],
                ["assistant", "Assistant", MessageSquare],
                ["activity", "Activity", ListOrdered],
              ] as const
            ).map(([id, label, Icon]) => (
              <button
                key={id}
                type="button"
                data-testid={`tab-${id}`}
                onClick={() => setScreen(id)}
                className={cn(
                  "relative flex flex-col items-center gap-0.5 py-1 text-[10.5px] font-medium",
                  screen === id ? "text-brand-700" : "text-slate-400 hover:text-slate-600",
                )}
              >
                <Icon className="size-5" />
                {label}
                {id === "assistant" && demo.chat.some((r) => r.approvals.some((a) => a.status === "pending")) && (
                  <span className="absolute right-[34%] top-0.5 size-2 rounded-full bg-rose-500" />
                )}
              </button>
            ))}
          </nav>
        </div>
      </div>
      <div className="min-h-0">
        <TracePanel run={traceRun} steps={demo.traceRunId ? demo.steps[demo.traceRunId] : undefined} live={live} />
      </div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-3 p-4">
      {[64, 120, 180].map((h) => (
        <div key={h} className="animate-pulse rounded-2xl bg-slate-200/70" style={{ height: h }} />
      ))}
    </div>
  );
}
