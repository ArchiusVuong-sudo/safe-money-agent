import { CircleAlert, CircleCheck, Loader2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { StepList } from "../components/StepList";
import { Badge } from "../components/ui/badge";
import { api } from "../lib/api";
import { cn } from "../lib/cn";
import { dateTime, ms, num } from "../lib/format";
import type { RunDetail, RunSummary } from "../lib/types";

export function RunsPage({ focusId }: { focusId: string | null }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [selected, setSelected] = useState<string | null>(focusId);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get<RunSummary[]>("/api/runs?limit=200");
      setRuns(r);
      setSelected((cur) => cur ?? r[0]?.id ?? null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load runs");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selected) return;
    let stop = false;
    const fetchOne = async () => {
      const d = await api.get<RunDetail>(`/api/runs/${selected}`);
      if (!stop) setDetail(d);
      return d;
    };
    void fetchOne();
    const t = setInterval(async () => {
      const d = await fetchOne();
      if (d.status !== "running") clearInterval(t);
    }, 1500);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, [selected]);

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_520px] gap-5 px-6 py-5">
      <section className="flex min-h-0 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm">
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <div>
            <h2 className="text-[14px] font-semibold">Runs</h2>
            <p className="text-[12px] text-slate-500">Every agent run is stored with its full trace. Tokens come from the SDK result message.</p>
          </div>
          <button type="button" onClick={() => void load()} className="text-[12px] font-medium text-brand-700 hover:underline">
            Refresh
          </button>
        </header>
        <div className="scroll-thin min-h-0 flex-1 overflow-auto">
          {error && <div className="p-5 text-[13px] text-rose-600">{error}</div>}
          {runs === null && !error && <div className="p-5 text-[13px] text-slate-400">Loading...</div>}
          {runs?.length === 0 && (
            <div className="p-10 text-center text-[13px] text-slate-500">No runs yet. Ask the assistant something, or run the evals.</div>
          )}
          {runs && runs.length > 0 && (
            <table className="w-full text-left text-[12px]" data-testid="runs-table">
              <thead className="sticky top-0 whitespace-nowrap bg-slate-50 text-[10.5px] font-medium uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-2">Run</th>
                  <th className="px-2 py-2">Mode</th>
                  <th className="px-2 py-2 text-right">Steps</th>
                  <th className="px-2 py-2 text-right">Input</th>
                  <th className="px-2 py-2 text-right">Output</th>
                  <th className="px-2 py-2 text-right">Cache write</th>
                  <th className="px-2 py-2 text-right">Cache read</th>
                  <th className="px-2 py-2 text-right">Cost</th>
                  <th className="px-2 py-2 text-right">Time</th>
                  <th className="px-4 py-2">Figures</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {runs.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => setSelected(r.id)}
                    className={cn("cursor-pointer hover:bg-slate-50", selected === r.id && "bg-brand-50/60 hover:bg-brand-50")}
                  >
                    <td className="max-w-[260px] px-4 py-2">
                      <div className="flex items-center gap-1.5">
                        {r.status === "running" ? (
                          <Loader2 className="size-3.5 animate-spin text-brand-600" />
                        ) : r.status === "error" ? (
                          <CircleAlert className="size-3.5 text-rose-600" />
                        ) : (
                          <CircleCheck className="size-3.5 text-emerald-600" />
                        )}
                        <span className="truncate font-medium text-slate-800">{r.prompt}</span>
                      </div>
                      <div className="pl-5 text-[11px] text-slate-400">
                        {dateTime(r.started_at)} · {r.kind === "eval" ? `eval ${r.case_id}` : "chat"}
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <Badge variant={r.provider === "live" ? "good" : "info"}>{r.provider}</Badge>
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums">{r.steps}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{num(r.input_tokens)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{num(r.output_tokens)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{num(r.cache_creation_tokens)}</td>
                    <td className="px-2 py-2 text-right tabular-nums">{num(r.cache_read_tokens)}</td>
                    <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">{r.cost_usd != null ? `$${r.cost_usd.toFixed(4)}` : "-"}</td>
                    <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums">{ms(r.duration_ms)}</td>
                    <td className="px-4 py-2">
                      {r.grounded === null ? (
                        <span className="text-slate-400">-</span>
                      ) : r.grounded ? (
                        <Badge variant="good">grounded</Badge>
                      ) : (
                        <Badge variant="bad" title={r.ungrounded.join(", ")}>
                          {r.ungrounded.length} ungrounded
                        </Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <section className="flex min-h-0 flex-col rounded-2xl border border-slate-200 bg-white shadow-sm" data-testid="run-detail">
        {!detail ? (
          <div className="flex flex-1 items-center justify-center text-[13px] text-slate-400">Select a run</div>
        ) : (
          <>
            <header className="border-b border-slate-100 px-5 py-3">
              <div className="flex items-center justify-between gap-2">
                <h2 className="truncate text-[14px] font-semibold">{detail.prompt}</h2>
                <span className="shrink-0 font-mono text-[11px] text-slate-400">{detail.id}</span>
              </div>
              <div className="mt-1 flex flex-wrap gap-1.5 text-[11px]">
                <Badge variant="outline">{detail.model}</Badge>
                <Badge variant="outline">{detail.num_turns ?? "-"} turns</Badge>
                <Badge variant="outline">{detail.cost_usd != null ? `$${detail.cost_usd.toFixed(4)}` : "no cost"}</Badge>
                <Badge variant="outline">{ms(detail.duration_ms)}</Badge>
              </div>
            </header>
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 py-4">
              <StepList steps={detail.trace} running={detail.status === "running"} />
            </div>
          </>
        )}
      </section>
    </div>
  );
}
