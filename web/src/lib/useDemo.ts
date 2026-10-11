import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { AppStateInfo, ChatRun, Home, RunDetail, Step, StreamEvent, Txn } from "./types";

export interface Demo {
  info: AppStateInfo | null;
  home: Home | null;
  txns: Txn[] | null;
  chat: ChatRun[];
  steps: Record<string, Step[]>;
  traceRunId: string | null;
  running: boolean;
  pendingMessage: string | null;
  error: string | null;
  loadError: string | null;
  send: (message: string) => Promise<void>;
  decide: (approvalId: string, decision: "approve" | "decline") => Promise<void>;
  reset: () => Promise<void>;
  showTrace: (runId: string) => void;
  clearError: () => void;
}

export function useDemo(): Demo {
  const [info, setInfo] = useState<AppStateInfo | null>(null);
  const [home, setHome] = useState<Home | null>(null);
  const [txns, setTxns] = useState<Txn[] | null>(null);
  const [chat, setChat] = useState<ChatRun[]>([]);
  const [steps, setSteps] = useState<Record<string, Step[]>>({});
  const [traceRunId, setTraceRunId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const source = useRef<EventSource | null>(null);

  const refreshMoney = useCallback(async () => {
    const [h, t] = await Promise.all([api.get<Home>("/api/home"), api.get<Txn[]>("/api/transactions?limit=80")]);
    setHome(h);
    setTxns(t);
  }, []);

  const refreshChat = useCallback(async () => {
    const c = await api.get<ChatRun[]>("/api/chat");
    setChat(c);
    return c;
  }, []);

  const loadTrace = useCallback(async (runId: string) => {
    const r = await api.get<RunDetail>(`/api/runs/${runId}`);
    setSteps((prev) => ({ ...prev, [runId]: r.trace }));
  }, []);

  const subscribe = useCallback(
    (runId: string) => {
      source.current?.close();
      setSteps((prev) => ({ ...prev, [runId]: [] }));
      setTraceRunId(runId);
      setRunning(true);
      const es = new EventSource(`/api/runs/${runId}/events`);
      source.current = es;
      es.onmessage = (msg) => {
        const ev = JSON.parse(msg.data as string) as StreamEvent;
        if (ev.type === "step") {
          setSteps((prev) => {
            const list = prev[runId] ?? [];
            if (list.some((s) => s.seq === ev.step.seq)) return prev;
            return { ...prev, [runId]: [...list, ev.step] };
          });
          if (ev.step.type === "permission") void refreshChat();
        } else if (ev.type === "approval_request" || ev.type === "approval_resolved") {
          void refreshChat();
        } else if (ev.type === "money_changed") {
          void refreshMoney();
        } else if (ev.type === "run_finished") {
          es.close();
          if (source.current === es) source.current = null;
          setRunning(false);
          setPendingMessage(null);
          void refreshChat();
          void refreshMoney();
        }
      };
      es.onerror = () => {
        // The browser retries on its own; if the run already ended, stop and reload.
        if (es.readyState === EventSource.CLOSED) {
          setRunning(false);
          void refreshChat();
        }
      };
    },
    [refreshChat, refreshMoney],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [i] = await Promise.all([api.get<AppStateInfo>("/api/state"), refreshMoney()]);
        if (cancelled) return;
        setInfo(i);
        const c = await refreshChat();
        const last = c[c.length - 1];
        if (last) {
          if (last.status === "running") subscribe(last.id);
          else {
            setTraceRunId(last.id);
            void loadTrace(last.id);
          }
        }
      } catch (e) {
        if (!cancelled) setLoadError(e instanceof Error ? e.message : "Could not reach the server");
      }
    })();
    return () => {
      cancelled = true;
      source.current?.close();
    };
  }, [loadTrace, refreshChat, refreshMoney, subscribe]);

  const send = useCallback(
    async (message: string) => {
      setError(null);
      setPendingMessage(message);
      try {
        const { run_id } = await api.post<{ run_id: string }>("/api/chat", { message });
        subscribe(run_id);
        void refreshChat();
      } catch (e) {
        setPendingMessage(null);
        setError(e instanceof Error ? e.message : "Could not send");
      }
    },
    [refreshChat, subscribe],
  );

  const decide = useCallback(
    async (approvalId: string, decision: "approve" | "decline") => {
      await api.post(`/api/approvals/${approvalId}`, { decision });
      await refreshChat();
    },
    [refreshChat],
  );

  const reset = useCallback(async () => {
    setError(null);
    try {
      await api.post("/api/reset");
      source.current?.close();
      setSteps({});
      setTraceRunId(null);
      setRunning(false);
      await Promise.all([refreshChat(), refreshMoney()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not reset");
    }
  }, [refreshChat, refreshMoney]);

  const showTrace = useCallback(
    (runId: string) => {
      setTraceRunId(runId);
      if (!steps[runId]) void loadTrace(runId);
    },
    [loadTrace, steps],
  );

  return {
    info,
    home,
    txns,
    chat,
    steps,
    traceRunId,
    running,
    pendingMessage,
    error,
    loadError,
    send,
    decide,
    reset,
    showTrace,
    clearError: () => setError(null),
  };
}
