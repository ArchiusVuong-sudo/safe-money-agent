import { ArrowUp, Info, ShieldAlert, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { cn } from "../lib/cn";
import { money } from "../lib/format";
import type { Approval, ChatRun, Step } from "../lib/types";
import { ApprovalCard } from "./ApprovalCard";

const TOOL_STATUS: Record<string, string> = {
  get_accounts: "Reading accounts",
  search_transactions: "Searching transactions",
  list_recurring: "Finding bills and paychecks",
  forecast: "Checking the forecast",
  simulate: "Testing a transfer against the policy",
  move_money: "Posting to the ledger",
  cancel_subscription: "Cancelling the subscription",
};

function liveStatus(steps: Step[]): string {
  const last = [...steps].reverse().find((s) => s.type === "tool_call" || s.type === "permission" || s.type === "approval");
  if (!last) return "Thinking";
  if (last.type === "permission") return last.data.decision === "ask_user" ? "Waiting for your approval" : "Policy refused a request, replanning";
  if (last.type === "approval") return "Finishing up";
  return TOOL_STATUS[last.name] ?? "Working";
}

export function AssistantScreen({
  chat,
  pendingMessage,
  running,
  liveSteps,
  suggestions,
  error,
  onSend,
  onDecide,
  onSelectRun,
  selectedRunId,
}: {
  chat: ChatRun[];
  pendingMessage: string | null;
  running: boolean;
  liveSteps: Step[];
  suggestions: string[];
  error: string | null;
  onSend: (m: string) => void;
  onDecide: (id: string, d: "approve" | "decline") => Promise<void>;
  onSelectRun: (id: string) => void;
  selectedRunId: string | null;
}) {
  const [text, setText] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const showPending = pendingMessage !== null && !chat.some((r) => r.status === "running");

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chat, pendingMessage, liveSteps.length]);

  const submit = (m: string) => {
    const msg = m.trim();
    if (!msg || running) return;
    setText("");
    onSend(msg);
  };

  return (
    <div className="flex h-full flex-col" data-testid="assistant-screen">
      <div className="scroll-thin flex-1 space-y-3 overflow-y-auto px-4 pb-3 pt-1">
        {chat.length === 0 && !showPending && (
          <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-white/60 p-5 text-center">
            <div className="mx-auto flex size-10 items-center justify-center rounded-full bg-brand-50 text-brand-600">
              <Sparkles className="size-5" />
            </div>
            <div className="mt-2 text-[14px] font-semibold">Ask about your money</div>
            <p className="mt-1 text-[12px] leading-snug text-slate-500">
              The assistant reads your data through typed tools. Any money move is checked by a fixed policy and waits for your approval.
            </p>
          </div>
        )}

        {chat.map((run) => (
          <RunBlock
            key={run.id}
            run={run}
            selected={run.id === selectedRunId}
            liveSteps={run.status === "running" ? liveSteps : []}
            onDecide={onDecide}
            onSelect={() => onSelectRun(run.id)}
          />
        ))}
        {showPending && (
          <>
            <UserBubble text={pendingMessage!} />
            <Typing label="Starting" />
          </>
        )}
        <div ref={bottom} />
      </div>

      <div className="border-t border-slate-200 bg-white/90 px-3 pb-3 pt-2 backdrop-blur">
        {!running && suggestions.length > 0 && (
          <div className="scroll-thin -mx-1 mb-2 flex gap-1.5 overflow-x-auto px-1 pb-1">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => submit(s)}
                className="shrink-0 rounded-full border border-slate-200 bg-white px-3 py-1 text-[11.5px] text-slate-600 hover:border-brand-300 hover:text-brand-700"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {error && <div className="mb-1.5 text-[11.5px] text-rose-600">{error}</div>}
        <form
          className="flex items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit(text);
          }}
        >
          <input
            data-testid="chat-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={running ? "The assistant is working..." : "Ask or tell the assistant"}
            disabled={running}
            className="h-10 min-w-0 flex-1 rounded-full border border-slate-200 bg-slate-50 px-4 text-[13px] outline-none focus:border-brand-400 focus:bg-white disabled:opacity-60"
          />
          <button
            type="submit"
            data-testid="chat-send"
            disabled={running || !text.trim()}
            className="flex size-10 items-center justify-center rounded-full bg-brand-600 text-white transition hover:bg-brand-700 disabled:bg-slate-300"
            aria-label="Send"
          >
            <ArrowUp className="size-4" />
          </button>
        </form>
      </div>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[82%] rounded-2xl rounded-br-md bg-ink px-3.5 py-2 text-[13px] leading-snug text-white">{text}</div>
    </div>
  );
}

function Typing({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-[12px] text-slate-500" data-testid="typing">
      <span className="flex gap-0.5">
        {[0, 1, 2].map((i) => (
          <span key={i} className="size-1.5 animate-bounce rounded-full bg-brand-500" style={{ animationDelay: `${i * 120}ms` }} />
        ))}
      </span>
      {label}...
    </div>
  );
}

function RunBlock({
  run,
  selected,
  liveSteps,
  onDecide,
  onSelect,
}: {
  run: ChatRun;
  selected: boolean;
  liveSteps: Step[];
  onDecide: (id: string, d: "approve" | "decline") => Promise<void>;
  onSelect: () => void;
}) {
  const byId = new Map<string, Approval>(run.approvals.map((a) => [a.id, a]));
  return (
    <div className="space-y-2">
      <UserBubble text={run.prompt} />
      {run.gate_steps
        .filter((s) => s.type === "permission")
        .map((s) => {
          if (s.data.decision === "ask_user") {
            const a = byId.get(s.data.approval_id as string);
            return a ? <ApprovalCard key={s.seq} approval={a} onDecide={onDecide} /> : null;
          }
          const input = s.data.input as Record<string, any> | undefined;
          const failed = (s.data.checks as { passed: boolean; label: string }[] | undefined)?.filter((c) => !c.passed) ?? [];
          return (
            <div key={s.seq} className="animate-fade-up flex gap-2 rounded-xl bg-amber-50 px-3 py-2 text-[11.5px] leading-snug text-amber-900" data-testid="policy-refusal">
              <ShieldAlert className="mt-px size-3.5 shrink-0 text-amber-600" />
              <span>
                The policy refused {input?.amount_usd !== undefined ? `a ${money(input.amount_usd)} transfer on ${input.date}` : "a request"}
                {failed.length > 0 ? ` (${failed.map((c) => c.label.toLowerCase()).join(", ")} failed)` : ""}. You were not asked.
              </span>
            </div>
          );
        })}
      {run.status === "running" ? (
        <Typing label={liveStatus(liveSteps)} />
      ) : (
        <div className="flex flex-col items-start gap-1">
          <div
            className={cn(
              "max-w-[88%] whitespace-pre-wrap rounded-2xl rounded-bl-md border bg-white px-3.5 py-2 text-[13px] leading-relaxed text-slate-800 shadow-sm",
              run.status === "error" ? "border-rose-200 text-rose-700" : "border-slate-200",
            )}
            data-testid="assistant-reply"
          >
            {run.status === "error" ? "Something went wrong on this run. The trace has the details." : run.final_text || "(no reply)"}
          </div>
          <button
            type="button"
            onClick={onSelect}
            className={cn(
              "ml-1 flex items-center gap-1 text-[10.5px] font-medium",
              selected ? "text-brand-700" : "text-slate-400 hover:text-slate-600",
            )}
          >
            <Info className="size-3" /> {selected ? "Showing trace" : "Show trace"}
            {run.grounded === false && <span className="text-rose-600"> · ungrounded figure</span>}
          </button>
        </div>
      )}
    </div>
  );
}
