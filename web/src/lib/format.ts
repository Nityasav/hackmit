export function money(cents: number): string {
  const sign = cents < 0 ? "−" : "";
  const abs = Math.abs(cents);
  return `${sign}$${(abs / 100).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function duration(seconds: number | null): string {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.round(seconds));
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
}

/** Splits "a **b** c" into [["a ", false], ["b", true], [" c", false]]. */
export function highlights(text: string): [string, boolean][] {
  return text.split("**").map((part, i) => [part, i % 2 === 1]);
}
