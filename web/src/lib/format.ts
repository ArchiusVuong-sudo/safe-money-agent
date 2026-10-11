const usdFmt = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function money(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  return usdFmt.format(v);
}

export function signedMoney(v: number): string {
  return v > 0 ? `+${usdFmt.format(v)}` : usdFmt.format(v);
}

export function compactMoney(v: number): string {
  const abs = Math.abs(v);
  const s = abs >= 1000 ? `$${(abs / 1000).toFixed(abs >= 10000 ? 0 : 1)}k` : `$${abs.toFixed(0)}`;
  return v < 0 ? `-${s}` : s;
}

export function num(v: number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  return v.toLocaleString("en-US");
}

export function ms(v: number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  return v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`;
}

export function time(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function shortDay(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  const dt = new Date(y!, (m ?? 1) - 1, d ?? 1);
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export const ACCOUNT_NAMES: Record<string, string> = {
  chk: "Checking",
  sav: "Savings",
  contact_riley: "Riley Park",
};

export function accountName(id: string): string {
  return ACCOUNT_NAMES[id] ?? id;
}
