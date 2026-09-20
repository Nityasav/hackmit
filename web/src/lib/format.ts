/** Cents to money, the one format the product renders figures in. */
export function money(cents: number): string {
  const sign = cents < 0 ? "−" : "";
  const abs = Math.abs(cents);
  return `${sign}$${(abs / 100).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/** A span of seconds, written the way a person reads a stopwatch. */
export function duration(seconds: number | null): string {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.round(seconds));
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`;
}

/**
 * Seconds between a task's start timestamp and `now`, or null when there is
 * nothing to measure from.
 *
 * The bundle records when a task started and never when it finished, so this
 * is time since the start and the screen has to say so. A task with no
 * `started_at`, an unparseable one, or a render with no clock yet returns
 * null, because a zero here would read as "just started".
 */
export function elapsedSeconds(startedAt: string | null, now: number | null): number | null {
  if (!startedAt || now === null) return null;
  const started = Date.parse(startedAt);
  if (Number.isNaN(started)) return null;
  return Math.max(0, (now - started) / 1000);
}
