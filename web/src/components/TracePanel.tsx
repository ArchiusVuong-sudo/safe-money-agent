import { Activity, Radio } from "lucide-react";
import { useEffect, useRef } from "react";
import type { ChatRun, Step } from "../lib/types";
import { StepList } from "./StepList";
import { Badge } from "./ui/badge";

export function TracePanel({ run, steps, live }: { run: ChatRun | null; steps: Step[] | undefined; live: boolean }) {
  const scroller = useRef<HTMLDivElement>(null);
  const count = steps?.length ?? 0;
  useEffect(() => {
    const el = scroller.current;
    if (el && live) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [count, live]);
  useEffect(() => {
    scroller.current?.scrollTo({ top: 0 });
  }, [run?.id]);
  return (
    <section className="flex h-full min-h-0 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm" data-testid="trace-panel">
      <header className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
        <div className="flex items-center gap-2">
          <Activity className="size-4 text-brand-600" />
          <h2 className="text-[14px] font-semibold">Under the hood</h2>
          {run && <span className="font-mono text-[11px] text-slate-400">{run.id}</span>}
        </div>
        <div className="flex items-center gap-2">
          {live ? (
            <Badge variant="brand">
              <Radio className="size-3" /> Streaming
            </Badge>
          ) : run ? (
            <Badge variant={run.status === "error" ? "bad" : "neutral"}>{run.status === "done" ? "Finished" : run.status}</Badge>
          ) : null}
        </div>
      </header>
      <div ref={scroller} className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {!run && (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="max-w-sm space-y-2">
              <div className="text-[14px] font-semibold text-slate-700">Every step of a run shows up here</div>
              <p className="text-[12.5px] leading-relaxed text-slate-500">
                Tool calls with arguments and timings, each permission decision with its policy checks, the approval, the ledger
                write, and the token and cache numbers of the run. Tap <span className="font-medium text-slate-700">Fix this</span> to
                start.
              </p>
            </div>
          </div>
        )}
        {run && steps === undefined && <div className="text-[12px] text-slate-400">Loading trace...</div>}
        {run && steps && <StepList steps={steps} running={live} />}
      </div>
    </section>
  );
}
