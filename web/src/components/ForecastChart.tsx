import { Area, ComposedChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { compactMoney, money } from "../lib/format";
import type { ForecastDay } from "../lib/types";

interface Props {
  days: ForecastDay[];
  floor: number;
  payday: string | null;
}

export function ForecastChart({ days, floor, payday }: Props) {
  const data = days.map((d) => ({ ...d, x: d.date }));
  const low = days.reduce<ForecastDay | null>((m, d) => (m === null || d.checking < m.checking ? d : m), null);
  const minY = Math.min(0, ...days.map((d) => d.checking));
  const maxY = Math.max(...days.map((d) => d.checking));
  const pad = (maxY - minY) * 0.12;
  const lowBound = minY < 0 ? minY - pad : 0;
  const ticks = niceTicks(lowBound, maxY + pad);
  const negative = low !== null && low.checking < 0;
  const scheduled = days.filter((d) => d.events.some((e) => e.kind === "scheduled" && e.account === "chk"));
  // Gradients use the shape's own bounding box (data max to data min), so split at zero there.
  const dataMin = Math.min(...days.map((d) => d.checking));
  const zeroFrac = dataMin < 0 && maxY > dataMin ? maxY / (maxY - dataMin) : 1;

  return (
    <div className="h-[168px] w-full" data-testid="forecast-chart" data-low={low?.checking ?? ""}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 10, right: 8, bottom: 0, left: -12 }}>
          <defs>
            <linearGradient id="chkFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0d9488" stopOpacity={0.28} />
              <stop offset={`${Math.max(0, Math.min(1, zeroFrac)) * 100}%`} stopColor="#0d9488" stopOpacity={0.06} />
              <stop offset={`${Math.max(0, Math.min(1, zeroFrac)) * 100}%`} stopColor="#e11d48" stopOpacity={0.18} />
              <stop offset="100%" stopColor="#e11d48" stopOpacity={0.3} />
            </linearGradient>
            <linearGradient id="chkStroke" x1="0" y1="0" x2="0" y2="1">
              <stop offset={`${Math.max(0, Math.min(1, zeroFrac)) * 100}%`} stopColor="#0d9488" />
              <stop offset={`${Math.max(0, Math.min(1, zeroFrac)) * 100}%`} stopColor="#e11d48" />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="x"
            tickLine={false}
            axisLine={false}
            interval={6}
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickFormatter={(v: string) => {
              const [, m, d] = v.split("-");
              return `${Number(m)}/${Number(d)}`;
            }}
          />
          <YAxis
            domain={[lowBound, maxY + pad]}
            tickLine={false}
            axisLine={false}
            width={48}
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickFormatter={(v: number) => compactMoney(v)}
            ticks={ticks}
          />
          <Tooltip
            cursor={{ stroke: "#cbd5e1", strokeDasharray: "3 3" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0]!.payload as ForecastDay;
              return (
                <div className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11px] shadow-md">
                  <div className="font-medium text-slate-500">{d.day}</div>
                  <div className={d.checking < 0 ? "font-semibold text-rose-600" : "font-semibold"}>{money(d.checking)}</div>
                  {d.events
                    .filter((e) => e.account === "chk")
                    .map((e, i) => (
                      <div key={i} className="text-slate-500">
                        {e.label}: {money(e.amount)}
                      </div>
                    ))}
                </div>
              );
            }}
          />
          <ReferenceLine y={0} stroke="#cbd5e1" />
          <ReferenceLine
            y={floor}
            stroke="#f59e0b"
            strokeDasharray="4 3"
            label={{ value: `Floor ${money(floor)}`, position: "insideTopRight", fontSize: 9, fill: "#b45309" }}
          />
          {payday && (
            <ReferenceLine
              x={payday}
              stroke="#94a3b8"
              strokeDasharray="2 3"
              label={{ value: "Payday", position: "insideTopLeft", fontSize: 9, fill: "#64748b" }}
            />
          )}
          <Area
            type="monotone"
            dataKey="checking"
            stroke="url(#chkStroke)"
            strokeWidth={2.2}
            fill="url(#chkFill)"
            isAnimationActive
            animationDuration={700}
            dot={false}
            activeDot={{ r: 3.5 }}
          />
          {scheduled.map((d) => (
            <ReferenceDot key={d.date} x={d.date} y={d.checking} r={4} fill="#6366f1" stroke="white" strokeWidth={1.5} />
          ))}
          {low && (
            <ReferenceDot
              x={low.date}
              y={low.checking}
              r={negative ? 5 : 4}
              fill={negative ? "#e11d48" : "#0d9488"}
              stroke="white"
              strokeWidth={2}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Round tick values (0 always included) inside [lo, hi]. */
export function niceTicks(lo: number, hi: number): number[] {
  const raw = (hi - lo) / 4;
  const mag = 10 ** Math.floor(Math.log10(Math.max(raw, 1)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(Math.round(v) || 0);
  return out;
}
