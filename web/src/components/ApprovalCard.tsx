import { ArrowRight, CalendarClock, CircleCheck, CircleX, Clock, ShieldCheck, XCircle } from "lucide-react";
import { useState } from "react";
import { cn } from "../lib/cn";
import { money, shortDay } from "../lib/format";
import type { Approval } from "../lib/types";
import { HoldButton } from "./HoldButton";

function LowRow({ label, before, after }: { label: string; before: number; after: number }) {
  return (
    <div className="flex items-center justify-between text-[13px]">
      <span className="text-slate-500">{label}</span>
      <span className="flex items-center gap-1.5 font-medium tabular-nums">
        <span className={before < 0 ? "text-rose-600" : "text-slate-700"}>{money(before)}</span>
        <ArrowRight className="size-3 text-slate-400" />
        <span className={after < 0 ? "text-rose-600" : "text-emerald-700"}>{money(after)}</span>
      </span>
    </div>
  );
}

export function ApprovalCard({
  approval,
  onDecide,
}: {
  approval: Approval;
  onDecide: (id: string, decision: "approve" | "decline") => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const p = approval.preview;
  const pending = approval.status === "pending";
  const transfer = p.kind === "transfer";

  const decide = async (d: "approve" | "decline") => {
    setBusy(true);
    setError(null);
    try {
      await onDecide(approval.id, d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send your answer");
      setBusy(false);
    }
  };

  return (
    <div
      data-testid="approval-card"
      data-status={approval.status}
      className={cn(
        "animate-fade-up overflow-hidden rounded-2xl border bg-white shadow-sm",
        pending ? "border-brand-200 ring-4 ring-brand-50" : "border-slate-200",
      )}
    >
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
          <ShieldCheck className="size-3.5 text-brand-600" />
          {transfer ? "Approve transfer" : "Approve cancellation"}
        </span>
        <StatusPill status={approval.status} />
      </div>

      <div className="space-y-3 px-4 py-3">
        {transfer ? (
          <>
            <div className="flex items-end justify-between">
              <div className="text-[26px] font-semibold leading-none tracking-tight tabular-nums">{money(p.amount_usd)}</div>
              <div className="flex items-center gap-1 text-xs font-medium text-slate-500">
                <CalendarClock className="size-3.5" />
                {p.when === "today" ? "Today" : `Scheduled ${p.day ?? shortDay(p.date ?? "")}`}
              </div>
            </div>
            <div className="flex items-center gap-2 text-[13px] font-medium text-slate-700">
              <span className="rounded-md bg-slate-100 px-2 py-1">{p.from?.name}</span>
              <ArrowRight className="size-3.5 text-slate-400" />
              <span className="rounded-md bg-slate-100 px-2 py-1">{p.to?.name}</span>
            </div>
            {p.low_points && (
              <div className="space-y-1 rounded-xl bg-slate-50 px-3 py-2">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                  {p.when === "today" ? "Lowest point, next 30 days" : `Lowest point from ${p.day ?? p.date}`}
                </div>
                {p.low_points.chk && <LowRow label="Checking" before={p.low_points.chk.before.usd} after={p.low_points.chk.after.usd} />}
                {p.low_points.sav && <LowRow label="Savings" before={p.low_points.sav.before.usd} after={p.low_points.sav.after.usd} />}
              </div>
            )}
          </>
        ) : (
          <>
            <div className="text-[17px] font-semibold">{p.name}</div>
            <div className="grid grid-cols-2 gap-2 text-[13px]">
              <div className="rounded-xl bg-slate-50 px-3 py-2">
                <div className="text-[11px] text-slate-400">Price now</div>
                <div className="font-semibold tabular-nums">
                  {money(p.amount_usd)}
                  {p.previous_amount_usd != null && p.previous_amount_usd !== p.amount_usd && (
                    <span className="ml-1.5 text-xs font-normal text-slate-400 line-through">{money(p.previous_amount_usd)}</span>
                  )}
                </div>
              </div>
              <div className="rounded-xl bg-slate-50 px-3 py-2">
                <div className="text-[11px] text-slate-400">Saves in 30 days</div>
                <div className="font-semibold tabular-nums text-emerald-700">{money(p.saves_next_30_days_usd)}</div>
              </div>
            </div>
            <div className="text-[11px] text-slate-400">Prototype: marks the series cancelled; no merchant is contacted.</div>
          </>
        )}

        <ul className="space-y-1">
          {p.checks.map((c) => (
            <li key={c.id} className="flex items-center gap-1.5 text-[12px] text-slate-600">
              {c.passed ? <CircleCheck className="size-3.5 text-emerald-600" /> : <CircleX className="size-3.5 text-rose-600" />}
              {c.label}
            </li>
          ))}
        </ul>
      </div>

      {pending && (
        <div className="flex gap-2 border-t border-slate-100 px-4 py-3">
          <button
            type="button"
            data-testid="decline"
            disabled={busy}
            onClick={() => void decide("decline")}
            className="h-11 rounded-xl border border-slate-200 px-4 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            Decline
          </button>
          <HoldButton disabled={busy} onConfirm={() => void decide("approve")} />
        </div>
      )}
      {error && <div className="px-4 pb-3 text-xs text-rose-600">{error}</div>}
    </div>
  );
}

function StatusPill({ status }: { status: Approval["status"] }) {
  const map = {
    pending: { cls: "bg-brand-50 text-brand-700", icon: <Clock className="size-3" />, text: "Waiting for you" },
    approved: { cls: "bg-emerald-50 text-emerald-700", icon: <CircleCheck className="size-3" />, text: "Approved" },
    declined: { cls: "bg-slate-100 text-slate-600", icon: <XCircle className="size-3" />, text: "Declined" },
    expired: { cls: "bg-amber-50 text-amber-700", icon: <Clock className="size-3" />, text: "Expired" },
  } as const;
  const m = map[status];
  return <span className={cn("flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium", m.cls)}>{m.icon}{m.text}</span>;
}
