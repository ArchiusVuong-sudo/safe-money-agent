import {
  AlertTriangle,
  BookCheck,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  CircleX,
  Cpu,
  Gauge,
  Hourglass,
  MessageSquare,
  RotateCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
  UserX,
  Wrench,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { cn } from "../lib/cn";
import { accountName, dayLabel, money, ms, num } from "../lib/format";
import type { PolicyCheck, Step } from "../lib/types";
import { Badge } from "./ui/badge";

type Item =
  | { kind: "tool"; call: Step; result: Step | null }
  | { kind: "step"; step: Step }
  | { kind: "waiting"; permission: Step };

const WRITE = new Set(["mcp__money__move_money", "mcp__money__cancel_subscription"]);

export function toItems(steps: Step[], running: boolean): Item[] {
  const used = new Set<number>();
  const items: Item[] = [];
  steps.forEach((s, i) => {
    if (used.has(s.seq)) return;
    if (s.type === "tool_call") {
      const result = steps.slice(i + 1).find((r) => r.type === "tool_result" && r.name === s.name && !used.has(r.seq)) ?? null;
      if (result) used.add(result.seq);
      items.push({ kind: "tool", call: s, result });
      return;
    }
    items.push({ kind: "step", step: s });
    if (s.type === "permission" && s.data.decision === "ask_user") {
      const answered = steps.some((a) => a.type === "approval" && a.data.approval_id === s.data.approval_id);
      if (!answered && running) items.push({ kind: "waiting", permission: s });
    }
  });
  return items;
}

function Row({
  icon,
  tone = "slate",
  title,
  right,
  children,
}: {
  icon: ReactNode;
  tone?: "slate" | "brand" | "green" | "red" | "amber" | "indigo";
  title: ReactNode;
  right?: ReactNode;
  children?: ReactNode;
}) {
  const tones = {
    slate: "bg-slate-100 text-slate-600",
    brand: "bg-brand-50 text-brand-700",
    green: "bg-emerald-50 text-emerald-700",
    red: "bg-rose-50 text-rose-700",
    amber: "bg-amber-50 text-amber-700",
    indigo: "bg-indigo-50 text-indigo-700",
  };
  return (
    <li className="group animate-fade-up relative flex gap-3 pb-4 last:pb-0">
      <div className="absolute bottom-0 left-[13px] top-7 w-px bg-slate-200 group-last:hidden" />
      <div className={cn("relative z-10 flex size-7 shrink-0 items-center justify-center rounded-lg", tones[tone])}>{icon}</div>
      <div className="min-w-0 flex-1 pt-0.5">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0 text-[13px] font-semibold text-slate-800">{title}</div>
          {right && <div className="shrink-0 text-[11px] tabular-nums text-slate-400">{right}</div>}
        </div>
        {children && <div className="mt-1 space-y-1.5 text-[12px] text-slate-600">{children}</div>}
      </div>
    </li>
  );
}

function Code({ value, max = 160 }: { value: unknown; max?: number }) {
  const text = JSON.stringify(value);
  return (
    <code className="block truncate rounded-md bg-slate-50 px-2 py-1 font-mono text-[11px] text-slate-600" title={text}>
      {text.length > max ? `${text.slice(0, max)}…` : text}
    </code>
  );
}

function Expand({ value }: { value: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-0.5 text-[11px] font-medium text-slate-400 hover:text-slate-600"
      >
        {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />} {open ? "Hide" : "Show"} result JSON
      </button>
      {open && (
        <pre className="scroll-thin mt-1 max-h-64 overflow-auto rounded-md bg-slate-900 p-2 font-mono text-[10.5px] leading-relaxed text-slate-100">
          {JSON.stringify(value, null, 2)}
        </pre>
      )}
    </div>
  );
}

function Checks({ checks }: { checks: PolicyCheck[] }) {
  return (
    <ul className="grid grid-cols-1 gap-0.5">
      {checks.map((c) => (
        <li key={c.id} className="flex items-start gap-1.5">
          {c.passed ? (
            <CircleCheck className="mt-px size-3.5 shrink-0 text-emerald-600" />
          ) : (
            <CircleX className="mt-px size-3.5 shrink-0 text-rose-600" />
          )}
          <span>
            <span className={cn("font-medium", c.passed ? "text-slate-700" : "text-rose-700")}>{c.label}</span>
            {!c.passed && <span className="text-rose-600"> - {c.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function argsLine(name: string, input: Record<string, any>): string {
  if (name === "move_money" || name === "simulate") {
    return `${money(input.amount_usd)} ${accountName(input.from_account)} to ${accountName(input.to_account)} on ${dayLabel(input.date)}`;
  }
  if (name === "cancel_subscription") return `cancel series ${input.series_id}`;
  return "";
}

function resultSummary(name: string, out: Record<string, any>): ReactNode {
  if (out.error) return <span className="text-rose-600">{String(out.error)}</span>;
  switch (name) {
    case "get_accounts":
      return (out.accounts as { name: string; balance_usd: number }[]).map((a) => `${a.name} ${money(a.balance_usd)}`).join(" · ");
    case "forecast": {
      const l = out.low_points?.chk;
      return l ? `Checking low ${money(l.low_usd)} on ${l.low_day} · payday ${out.next_payday_day}` : "";
    }
    case "simulate":
      return (
        <span className={out.would_pass_policy ? "text-emerald-700" : "text-rose-600"}>
          {out.would_pass_policy ? "Would pass the policy" : `Would fail: ${(out.failed as string[]).join(", ")}`}
          {out.preview?.low_points?.chk && ` · checking low after ${money(out.preview.low_points.chk.after.usd)}`}
        </span>
      );
    case "list_recurring": {
      const s = out.series as { price_changed: boolean }[];
      return `${s.length} series found · ${s.filter((x) => x.price_changed).length} price change`;
    }
    case "search_transactions":
      return `${out.count} transactions · merchant and memo returned as untrusted`;
    case "move_money":
      return `${out.status} · entry #${out.entry_id}${out.already_posted ? " (already posted)" : ""}`;
    case "cancel_subscription":
      return `${out.untrusted?.merchant ?? out.series_id} cancelled (simulated)`;
    default:
      return "";
  }
}

function StepRow({ step }: { step: Step }) {
  const d = step.data;
  switch (step.type) {
    case "user":
      return (
        <Row icon={<MessageSquare className="size-3.5" />} title="User message">
          <p className="text-[13px] text-slate-700">{d.message}</p>
        </Row>
      );
    case "init": {
      const tools = (d.tools as string[] | undefined) ?? [];
      return (
        <Row
          icon={<Cpu className="size-3.5" />}
          title={d.replay_of ? "Replaying a recorded live session" : "Agent session started"}
          right={d.model}
        >
          <div className="flex flex-wrap gap-1">
            {tools.map((t) => {
              const short = t.replace("mcp__money__", "");
              const w = WRITE.has(t);
              return (
                <span
                  key={t}
                  className={cn(
                    "rounded-md px-1.5 py-0.5 font-mono text-[10.5px]",
                    w ? "bg-amber-50 text-amber-800 ring-1 ring-amber-600/20" : "bg-emerald-50 text-emerald-800",
                  )}
                  title={w ? "Write tool: goes through the permission gate" : "Read tool: auto-allowed"}
                >
                  {short}
                </span>
              );
            })}
          </div>
          <div className="text-[11px] text-slate-400">
            {tools.length} tools, no built-in tools · read tools auto-allowed · write tools gated
            {d.replay_of && ` · recorded ${dayLabel(d.replay_of)}`}
          </div>
        </Row>
      );
    }
    case "permission": {
      const ask = d.decision === "ask_user";
      const policyDeny = d.by === "policy" && d.decision === "deny";
      return (
        <Row
          icon={ask ? <ShieldCheck className="size-3.5" /> : <ShieldAlert className="size-3.5" />}
          tone={ask ? "brand" : "red"}
          title={
            <span className="flex items-center gap-2">
              Permission gate · {step.name}
              <Badge variant={ask ? "brand" : "bad"}>{ask ? "Policy passed, asking the user" : policyDeny ? "Refused by policy" : "Denied"}</Badge>
            </span>
          }
          right={ms(step.ms)}
        >
          {d.input && argsLine(step.name, d.input) && <div className="font-medium text-slate-700">{argsLine(step.name, d.input)}</div>}
          {d.checks ? <Checks checks={d.checks} /> : <div className="text-rose-600">{d.reason}</div>}
          {policyDeny && d.hints && Object.keys(d.hints).length > 0 && (
            <div className="flex flex-wrap gap-1 pt-0.5">
              {d.hints.max_safe_today_usd !== undefined && <Badge variant="outline">Max safe today {money(d.hints.max_safe_today_usd)}</Badge>}
              {d.hints.next_payday_day && <Badge variant="outline">Next payday {d.hints.next_payday_day}</Badge>}
              {d.hints.max_safe_on_next_payday_usd !== undefined && (
                <Badge variant="outline">Max safe on payday {money(d.hints.max_safe_on_next_payday_usd)}</Badge>
              )}
              <span className="text-[11px] text-slate-400">Hints sent back to the agent. The user is never asked.</span>
            </div>
          )}
        </Row>
      );
    }
    case "approval": {
      const ok = d.decision === "approved";
      return (
        <Row
          icon={ok ? <UserCheck className="size-3.5" /> : <UserX className="size-3.5" />}
          tone={ok ? "green" : "amber"}
          title={ok ? "Approved by the user" : d.decision === "declined" ? "Declined by the user" : "Request expired (no answer)"}
          right={ms(step.ms)}
        />
      );
    }
    case "ledger_write": {
      if (step.name === "cancel_subscription") {
        return (
          <Row icon={<BookCheck className="size-3.5" />} tone="indigo" title="Series cancelled">
            <div>
              <span className="font-mono">{d.series_id}</span> marked cancelled{d.already_cancelled ? " (already was)" : ""} · simulated
            </div>
          </Row>
        );
      }
      return (
        <Row
          icon={<BookCheck className="size-3.5" />}
          tone="indigo"
          title={`Ledger write · entry #${d.entry_id} · ${d.status}${d.already_posted ? " (no new rows)" : ""}`}
        >
          <div className="overflow-hidden rounded-md border border-slate-200">
            {(d.legs as { account: string; amount_usd: number }[]).map((l) => (
              <div key={l.account} className="flex justify-between border-b border-slate-100 px-2 py-1 last:border-0">
                <span>{accountName(l.account)}</span>
                <span className={cn("font-mono tabular-nums", l.amount_usd < 0 ? "text-rose-600" : "text-emerald-700")}>
                  {l.amount_usd > 0 ? "+" : ""}
                  {money(l.amount_usd)}
                </span>
              </div>
            ))}
          </div>
          <div className="text-[11px] text-slate-400">
            Two legs sum to zero · idempotency key <span className="font-mono text-slate-500">{d.idempotency_key}</span> · date {dayLabel(d.date)}
          </div>
        </Row>
      );
    }
    case "assistant_text":
      return (
        <Row icon={<Sparkles className="size-3.5" />} tone="brand" title="Assistant">
          <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-slate-700">{d.text}</p>
        </Row>
      );
    case "result": {
      const cells: [string, string][] = [
        ["Input", num(d.input_tokens)],
        ["Output", num(d.output_tokens)],
        ["Cache write", num(d.cache_creation_tokens)],
        ["Cache read", num(d.cache_read_tokens)],
        ["Cost", d.cost_usd != null ? `$${Number(d.cost_usd).toFixed(4)}` : "-"],
        ["Time", ms(d.duration_ms)],
      ];
      return (
        <Row
          icon={<Gauge className="size-3.5" />}
          title={
            <span className="flex items-center gap-2">
              Run finished
              {d.grounded ? (
                <Badge variant="good">Figures grounded ({(d.figures as string[]).length})</Badge>
              ) : (
                <Badge variant="bad">Ungrounded: {(d.ungrounded as string[]).join(", ")}</Badge>
              )}
            </span>
          }
          right={d.num_turns != null ? `${d.num_turns} turns` : undefined}
        >
          <div className="grid grid-cols-3 gap-1 @xl:grid-cols-6">
            {cells.map(([k, v]) => (
              <div key={k} className="rounded-md bg-slate-50 px-2 py-1">
                <div className="text-[10px] text-slate-400">{k}</div>
                <div className="font-mono text-[11.5px] font-medium tabular-nums text-slate-700">{v}</div>
              </div>
            ))}
          </div>
          {d.provider === "replay" && <div className="text-[11px] text-slate-400">Token numbers are from the recorded live run.</div>}
        </Row>
      );
    }
    case "retry":
      return (
        <Row icon={<RotateCw className="size-3.5" />} tone="amber" title={`Retrying after a busy API (attempt ${d.attempt})`} right={`${d.wait_s} s`}>
          <div className="truncate">{d.error}</div>
        </Row>
      );
    case "rate_limit":
      return <Row icon={<AlertTriangle className="size-3.5" />} tone="amber" title="Rate limited" />;
    case "error":
      return (
        <Row icon={<AlertTriangle className="size-3.5" />} tone="red" title="Run error">
          <div className="break-words text-rose-600">{d.error}</div>
        </Row>
      );
    default:
      return <Row icon={<Cpu className="size-3.5" />} title={step.type} />;
  }
}

export function StepList({ steps, running }: { steps: Step[]; running: boolean }) {
  const items = toItems(steps, running);
  return (
    <ol className="@container relative" data-testid="trace-steps">
      {items.map((it) => {
        if (it.kind === "tool") {
          const out = (it.result?.data.output ?? {}) as Record<string, any>;
          const write = it.call.name === "move_money" || it.call.name === "cancel_subscription";
          return (
            <Row
              key={`t${it.call.seq}`}
              icon={<Wrench className="size-3.5" />}
              tone={write ? "indigo" : "slate"}
              title={
                <span className="flex items-center gap-2">
                  <span className="font-mono text-[12.5px]">{it.call.name}</span>
                  {write && <Badge variant="info">write, approved</Badge>}
                </span>
              }
              right={it.result ? ms(it.result.ms) : "running"}
            >
              <Code value={it.call.data.input} />
              {it.result && <div>{resultSummary(it.call.name, out)}</div>}
              {it.result && <Expand value={out} />}
            </Row>
          );
        }
        if (it.kind === "waiting") {
          return (
            <Row key={`w${it.permission.seq}`} icon={<Hourglass className="size-3.5" />} tone="brand" title="Waiting for the person to approve">
              <div className="flex items-center gap-2 text-[11px] text-slate-500">
                <span className="animate-pulse-ring size-2 rounded-full bg-brand-500" />
                The agent is paused inside the SDK permission callback. It denies after 5 minutes with no answer.
              </div>
            </Row>
          );
        }
        return <StepRow key={`s${it.step.seq}`} step={it.step} />;
      })}
    </ol>
  );
}
