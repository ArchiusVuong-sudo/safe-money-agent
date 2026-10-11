import { CircleCheck, CircleDashed, CircleX, Loader2, Play } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { dateTime, ms, num } from "../lib/format";
import type { AppStateInfo, EvalRun } from "../lib/types";

export function EvalsPage({ info, onOpenRun }: { info: AppStateInfo | null; onOpenRun: (runId: string) => void }) {
  const [ev, setEv] = useState<EvalRun | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const poll = useCallback(async (id?: string) => {
    const data = id ? await api.get<EvalRun>(`/api/evals/${id}`) : await api.get<EvalRun | null>("/api/evals/latest");
    setEv(data);
    return data;
  }, []);

  const watch = useCallback(
    (id: string) => {
      if (timer.current) clearInterval(timer.current);
      timer.current = setInterval(async () => {
        const d = await poll(id);
        if (d && d.status !== "running" && timer.current) {
          clearInterval(timer.current);
          timer.current = null;
        }
      }, 1000);
    },
    [poll],
  );

  useEffect(() => {
    void (async () => {
      try {
        const d = await poll();
        if (d && d.status === "running") watch(d.id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load evals");
      }
    })();
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [poll, watch]);

  const runAll = async () => {
    setError(null);
    try {
      const { eval_id } = await api.post<{ eval_id: string }>("/api/evals/run");
      await poll(eval_id);
      watch(eval_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start");
    }
  };

  const running = ev?.status === "running";
  const s = ev?.summary;

  return (
    <div className="h-full min-h-0 overflow-y-auto px-6 py-5 scroll-thin">
      <div className="mx-auto max-w-[1240px] space-y-4">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-[20px] font-semibold tracking-tight">Scenario evals</h1>
            <p className="mt-0.5 max-w-3xl text-[13px] text-slate-500">
              Eight cases run {info?.mode === "replay" ? "from recorded live runs" : "live"}, 3 at a time. Each gets its own copy of the
              synthetic data, its own tool server and an auto-approve or auto-decline answer. Code checks on the stored trace grade each
              case. No model grades a model.
            </p>
          </div>
          <Button variant="brand" size="lg" onClick={() => void runAll()} disabled={running} data-testid="run-all">
            {running ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
            {running ? "Running" : "Run all"}
          </Button>
        </div>

        {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-[13px] text-rose-700">{error}</div>}

        {ev === undefined && <div className="text-[13px] text-slate-400">Loading...</div>}
        {ev === null && (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-[13px] text-slate-500">
            No eval run yet. Press <span className="font-medium text-slate-700">Run all</span> to start.
          </div>
        )}

        {ev && s && (
          <>
            <div className="grid grid-cols-4 gap-3" data-testid="eval-summary">
              <Stat label="Cases passed" value={`${s.passed} / ${s.cases}`} tone={s.finished === s.cases ? (s.passed === s.cases ? "good" : "bad") : "neutral"} />
              <Stat label="Checks passed" value={`${s.checks_passed} / ${s.checks}`} />
              <Stat label="Mode" value={ev.provider === "live" ? `Live · ${ev.model}` : `Replay · ${ev.model}`} />
              <Stat label="Started" value={dateTime(ev.started_at)} sub={running ? `${s.finished} of ${s.cases} finished` : "finished"} />
            </div>

            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <table className="w-full text-left text-[12.5px]" data-testid="eval-table">
                <thead className="whitespace-nowrap bg-slate-50 text-[11px] font-medium uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="w-[260px] px-4 py-2">Case</th>
                    <th className="px-2 py-2">Checks</th>
                    <th className="px-2 py-2 text-right">In / out</th>
                    <th className="px-2 py-2 text-right">Cache read</th>
                    <th className="px-2 py-2 text-right">Time</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {ev.cases.map((c) => (
                    <tr key={c.id} data-testid={`eval-${c.id}`} data-status={c.status} className="align-top">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <StatusIcon status={c.status} />
                          <span className="font-semibold">{c.title}</span>
                          {c.approver === "declined" && <Badge variant="outline">auto-decline</Badge>}
                        </div>
                        <div className="mt-0.5 pl-6 text-[11.5px] text-slate-500">"{c.prompt}"</div>
                      </td>
                      <td className="px-2 py-3">
                        <div className="flex flex-wrap gap-1">
                          {c.checks.map((k) => (
                            <span
                              key={k.id}
                              title={k.detail}
                              className={cn(
                                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
                                k.passed === null
                                  ? "bg-slate-100 text-slate-500"
                                  : k.passed
                                    ? "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20"
                                    : "bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-600/20",
                              )}
                            >
                              {k.passed === null ? <CircleDashed className="size-3" /> : k.passed ? <CircleCheck className="size-3" /> : <CircleX className="size-3" />}
                              {k.label}
                            </span>
                          ))}
                        </div>
                        {c.error && <div className="mt-1 text-[11px] text-rose-600">{c.error}</div>}
                      </td>
                      <td className="px-2 py-3 text-right tabular-nums text-slate-600">
                        {c.run?.input_tokens != null ? `${num(c.run.input_tokens)} / ${num(c.run.output_tokens)}` : "-"}
                      </td>
                      <td className="px-2 py-3 text-right tabular-nums text-slate-600">{num(c.run?.cache_read_tokens)}</td>
                      <td className="whitespace-nowrap px-2 py-3 text-right tabular-nums text-slate-600">{ms(c.run?.duration_ms)}</td>
                      <td className="px-4 py-3 text-right">
                        {c.run && (
                          <button type="button" onClick={() => onOpenRun(c.run!.id)} className="text-[12px] font-medium text-brand-700 hover:underline">
                            Trace
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "passed") return <CircleCheck className="size-4 text-emerald-600" />;
  if (status === "failed" || status === "error") return <CircleX className="size-4 text-rose-600" />;
  if (status === "running") return <Loader2 className="size-4 animate-spin text-brand-600" />;
  return <CircleDashed className="size-4 text-slate-300" />;
}

function Stat({ label, value, sub, tone = "neutral" }: { label: string; value: string; sub?: string; tone?: "good" | "bad" | "neutral" }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className={cn("mt-0.5 text-[18px] font-semibold tabular-nums", tone === "good" && "text-emerald-700", tone === "bad" && "text-rose-700")}>
        {value}
      </div>
      {sub && <div className="text-[11px] text-slate-400">{sub}</div>}
    </div>
  );
}
