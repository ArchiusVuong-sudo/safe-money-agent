import { Check } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "../lib/cn";

const HOLD_MS = 900;

/** Press and hold to confirm. Holding the Space key works too. */
export function HoldButton({
  onConfirm,
  disabled,
  label = "Hold to approve",
}: {
  onConfirm: () => void;
  disabled?: boolean;
  label?: string;
}) {
  const [progress, setProgress] = useState(0);
  const [done, setDone] = useState(false);
  const start = useRef<number | null>(null);
  const frame = useRef<number | null>(null);
  const confirmRef = useRef(onConfirm);
  confirmRef.current = onConfirm;

  const stop = useCallback(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
    start.current = null;
  }, []);

  const tick = useCallback(
    (now: number) => {
      if (start.current === null) start.current = now;
      const p = Math.min(1, (now - start.current) / HOLD_MS);
      setProgress(p);
      if (p >= 1) {
        stop();
        setDone(true);
        confirmRef.current();
        return;
      }
      frame.current = requestAnimationFrame(tick);
    },
    [stop],
  );

  const begin = useCallback(() => {
    if (disabled || done || frame.current !== null) return;
    frame.current = requestAnimationFrame(tick);
  }, [disabled, done, tick]);

  const cancel = useCallback(() => {
    if (done) return;
    stop();
    setProgress(0);
  }, [done, stop]);

  useEffect(() => {
    if (disabled || done) return;
    const down = (e: KeyboardEvent) => {
      if (e.code !== "Space" || e.repeat) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      e.preventDefault();
      begin();
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === "Space") cancel();
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, [begin, cancel, disabled, done]);

  useEffect(() => stop, [stop]);

  const r = 11;
  const c = 2 * Math.PI * r;
  return (
    <button
      type="button"
      data-testid="hold-approve"
      disabled={disabled}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        begin();
      }}
      onPointerUp={cancel}
      onPointerCancel={cancel}
      onContextMenu={(e) => e.preventDefault()}
      className={cn(
        "relative flex h-11 flex-1 touch-none select-none items-center justify-center gap-2.5 overflow-hidden rounded-xl text-sm font-semibold text-white transition-colors",
        done ? "bg-emerald-600" : "bg-brand-600 hover:bg-brand-700",
        disabled && "opacity-50",
      )}
    >
      <span
        className="absolute inset-y-0 left-0 bg-brand-900/25"
        style={{ width: `${progress * 100}%`, transition: progress === 0 ? "width 150ms" : "none" }}
      />
      {done ? (
        <Check className="relative size-5" />
      ) : (
      <svg width="26" height="26" viewBox="0 0 26 26" className="relative -rotate-90">
        <circle cx="13" cy="13" r={r} fill="none" stroke="rgb(255 255 255 / 0.3)" strokeWidth="2.5" />
        <circle
          cx="13"
          cy="13"
          r={r}
          fill="none"
          stroke="white"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - progress)}
        />
      </svg>
      )}
      <span className="relative">{done ? "Approved" : label}</span>
    </button>
  );
}
