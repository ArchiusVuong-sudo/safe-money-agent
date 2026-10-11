import { ArrowDownLeft, ArrowUpRight, FileWarning, MessageCircleQuestion, X } from "lucide-react";
import { useMemo, useState } from "react";
import { cn } from "../lib/cn";
import { accountName, money } from "../lib/format";
import type { Txn } from "../lib/types";

export function ActivityScreen({ txns, onAsk, busy }: { txns: Txn[]; onAsk: (q: string) => void; busy: boolean }) {
  const [open, setOpen] = useState<Txn | null>(null);
  const groups = useMemo(() => {
    const m = new Map<string, Txn[]>();
    for (const t of txns) {
      const list = m.get(t.day) ?? [];
      list.push(t);
      m.set(t.day, list);
    }
    return [...m.entries()];
  }, [txns]);

  return (
    <div className="relative h-full" data-testid="activity-screen">
      <div className="scroll-thin h-full overflow-y-auto px-4 pb-4 pt-1">
        <div className="mb-2 text-[20px] font-semibold tracking-tight">Activity</div>
        {groups.length === 0 && <div className="py-10 text-center text-[13px] text-slate-400">No transactions yet.</div>}
        {groups.map(([day, list]) => (
          <div key={day} className="mb-3">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{day}</div>
            <ul className="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              {list.map((t) => (
                <li key={t.posting_id}>
                  <button
                    type="button"
                    data-testid={`txn-${t.kind}`}
                    onClick={() => setOpen(t)}
                    className="flex w-full items-center gap-2.5 px-3 py-2 text-left hover:bg-slate-50"
                  >
                    <div
                      className={cn(
                        "flex size-7 shrink-0 items-center justify-center rounded-full",
                        t.amount > 0 ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-500",
                      )}
                    >
                      {t.amount > 0 ? <ArrowDownLeft className="size-3.5" /> : <ArrowUpRight className="size-3.5" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12.5px] font-medium">{t.merchant}</div>
                      <div className="flex items-center gap-1 truncate text-[11px] text-slate-400">
                        {t.status === "scheduled" && <span className="font-medium text-indigo-600">Scheduled · </span>}
                        {accountName(t.account)} · {t.category}
                        {t.memo && t.source === "feed" && <span className="rounded bg-amber-50 px-1 text-[10px] font-medium text-amber-700">memo</span>}
                      </div>
                    </div>
                    <div className={cn("text-[12.5px] font-semibold tabular-nums", t.amount > 0 && "text-emerald-700")}>
                      {t.amount > 0 ? "+" : ""}
                      {money(t.amount)}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {open && (
        <div className="absolute inset-0 z-20 flex items-end bg-slate-900/30" onClick={() => setOpen(null)}>
          <div className="animate-fade-up w-full rounded-t-3xl bg-white p-4 shadow-xl" onClick={(e) => e.stopPropagation()} data-testid="txn-sheet">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-[12px] text-slate-400">{open.day} · {accountName(open.account)}</div>
                <div className="text-[17px] font-semibold">{open.merchant}</div>
              </div>
              <button type="button" onClick={() => setOpen(null)} className="rounded-full p-1 text-slate-400 hover:bg-slate-100" aria-label="Close">
                <X className="size-4" />
              </button>
            </div>
            <div className={cn("mt-2 text-[28px] font-semibold tabular-nums", open.amount > 0 && "text-emerald-700")}>{money(open.amount)}</div>
            <div className="mt-1 text-[12px] text-slate-500">
              {open.category} · {open.kind === "p2p" ? "person-to-person payment" : open.kind}
            </div>
            {open.memo && open.source === "agent" && <div className="mt-2 text-[12px] text-slate-500">Note: {open.memo}</div>}
            {open.memo && open.source === "feed" && (
              <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3">
                <div className="mb-1 flex items-center gap-1 text-[10.5px] font-semibold uppercase tracking-wide text-amber-700">
                  <FileWarning className="size-3" /> Memo, raw text from the feed
                </div>
                <p className="font-mono text-[11.5px] leading-snug text-amber-950">{open.memo}</p>
                <p className="mt-1.5 text-[10.5px] text-amber-700">The assistant gets this text in an untrusted field and treats it as data.</p>
              </div>
            )}
            <button
              type="button"
              data-testid="txn-question"
              disabled={busy}
              onClick={() => {
                const q = `What is the ${money(Math.abs(open.amount))} payment to ${open.merchant} about?`;
                setOpen(null);
                onAsk(q);
              }}
              className="mt-3 flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-ink text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
            >
              <MessageCircleQuestion className="size-4" /> Ask the assistant about this
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
