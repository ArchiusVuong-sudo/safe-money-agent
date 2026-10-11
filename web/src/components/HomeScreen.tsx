import { AlertTriangle, ArrowDownLeft, ArrowUpRight, CalendarClock, PiggyBank, ShieldCheck, Sparkles, Wallet } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../lib/cn";
import { money, shortDay } from "../lib/format";
import type { Home } from "../lib/types";
import { ForecastChart } from "./ForecastChart";

export function HomeScreen({ home, onFix, busy }: { home: Home; onFix: () => void; busy: boolean }) {
  const chk = home.accounts.find((a) => a.id === "chk");
  const sav = home.accounts.find((a) => a.id === "sav");
  const alert = home.alert;
  const upcoming = home.forecast
    .slice(1, 12)
    .flatMap((d) => d.events.filter((e) => e.account === "chk").map((e) => ({ ...e, date: d.date, day: d.day })))
    .slice(0, 5);

  return (
    <div className="space-y-3 px-4 pb-4 pt-1" data-testid="home-screen">
      <div>
        <div className="text-[12px] font-medium text-slate-400">{new Date(home.today + "T12:00:00").toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}</div>
        <div className="text-[20px] font-semibold tracking-tight">Hi {home.household.split(" ")[0]}</div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <BalanceCard icon={<Wallet className="size-4" />} label="Checking" value={chk?.balance ?? 0} testId="balance-chk" />
        <BalanceCard icon={<PiggyBank className="size-4" />} label="Savings" value={sav?.balance ?? 0} testId="balance-sav" />
      </div>

      {alert?.kind === "overdraft" ? (
        <div className="animate-fade-up rounded-2xl border border-rose-200 bg-rose-50 p-3.5" data-testid="overdraft-alert">
          <div className="flex gap-2.5">
            <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-600">
              <AlertTriangle className="size-4" />
            </div>
            <div className="min-w-0">
              <div className="text-[14px] font-semibold text-rose-900">
                Checking could hit {money(alert.low)} on {alert.low_day}
              </div>
              <div className="mt-0.5 text-[12px] leading-snug text-rose-800/80">
                Below $0 from {alert.first_below_zero_day}
                {alert.before_payday && home.next_payday_day ? `, before payday on ${home.next_payday_day}` : ""}.
              </div>
            </div>
          </div>
          <button
            type="button"
            data-testid="fix-this"
            disabled={busy}
            onClick={onFix}
            className="mt-3 flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-rose-600 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-700 disabled:opacity-60"
          >
            <Sparkles className="size-4" /> Fix this
          </button>
        </div>
      ) : (
        <div className="animate-fade-up flex items-center gap-2.5 rounded-2xl border border-emerald-200 bg-emerald-50 p-3.5" data-testid="on-track">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
            <ShieldCheck className="size-4" />
          </div>
          <div className="text-[13px] leading-snug text-emerald-900">
            <span className="font-semibold">On track.</span> Lowest checking balance in 30 days is {money(home.low.amount)} on {home.low.day}.
          </div>
        </div>
      )}

      <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <div className="mb-1 flex items-center justify-between">
          <div className="text-[13px] font-semibold">Checking, next 30 days</div>
          <div className="text-[10.5px] text-slate-400">Forecast computed in code</div>
        </div>
        <ForecastChart days={home.forecast} floor={home.floors.chk ?? 50} payday={home.next_payday} />
        <div className="mt-1 flex items-center gap-3 text-[10.5px] text-slate-500">
          <span className="flex items-center gap-1">
            <span className="size-2 rounded-full bg-rose-600" /> Low point
          </span>
          <span className="flex items-center gap-1">
            <span className="h-0 w-3 border-t border-dashed border-amber-500" /> $50 floor
          </span>
          {home.scheduled.length > 0 && (
            <span className="flex items-center gap-1">
              <span className="size-2 rounded-full bg-indigo-500" /> Scheduled
            </span>
          )}
          <span className="ml-auto">Avg spend {money(home.avg_daily_spend)}/day</span>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between px-3 pb-1 pt-2.5">
          <div className="text-[13px] font-semibold">Coming up</div>
          <CalendarClock className="size-3.5 text-slate-400" />
        </div>
        <ul className="divide-y divide-slate-100">
          {upcoming.map((e, i) => (
            <li key={i} className="flex items-center gap-2.5 px-3 py-2">
              <div
                className={cn(
                  "flex size-7 items-center justify-center rounded-full",
                  e.amount > 0 ? "bg-emerald-50 text-emerald-600" : e.kind === "scheduled" ? "bg-indigo-50 text-indigo-600" : "bg-slate-100 text-slate-500",
                )}
              >
                {e.amount > 0 ? <ArrowDownLeft className="size-3.5" /> : <ArrowUpRight className="size-3.5" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[12.5px] font-medium">{e.label}</div>
                <div className="text-[11px] text-slate-400">{e.kind === "scheduled" ? `Scheduled · ${e.day}` : shortDay(e.date)}</div>
              </div>
              <div className={cn("text-[12.5px] font-semibold tabular-nums", e.amount > 0 && "text-emerald-700")}>
                {e.amount > 0 ? "+" : ""}
                {money(e.amount)}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function BalanceCard({ icon, label, value, testId }: { icon: ReactNode; label: string; value: number; testId: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-center gap-1.5 text-[12px] font-medium text-slate-500">
        <span className="text-brand-600">{icon}</span>
        {label}
      </div>
      <div className="mt-1 text-[19px] font-semibold tracking-tight tabular-nums" data-testid={testId}>
        {money(value)}
      </div>
    </div>
  );
}
