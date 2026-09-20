/**
 * A marker that this browser has signed in before.
 *
 * The Supabase session itself lives in its own cookies and is what actually
 * authenticates a request — proxy.ts turns anyone without a valid one back to
 * the login screen. This cookie carries no authority at all. It only lets the
 * login screen greet a returning person differently, and it is cleared on sign
 * out so a shared machine does not imply the last user.
 */
export const RETURNING_COOKIE = "schooltrace.returning";

const ONE_YEAR_SECONDS = 60 * 60 * 24 * 365;

export function markReturningVisitor(): void {
  if (typeof document === "undefined") return;
  const secure = location.protocol === "https:" ? "; Secure" : "";
  // Lax rather than None: it is only ever read on our own pages.
  document.cookie = `${RETURNING_COOKIE}=1; Path=/; Max-Age=${ONE_YEAR_SECONDS}; SameSite=Lax${secure}`;
}

export function clearReturningVisitor(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${RETURNING_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax`;
}

export function hasReturningCookie(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie.split("; ").some((c) => c.startsWith(`${RETURNING_COOKIE}=`));
}

/**
 * Subscribe/snapshot pair for useSyncExternalStore.
 *
 * The cookie never changes while a page is open, so subscribe is a no-op. The
 * server snapshot is false because the server cannot read document.cookie,
 * and returning a different value there would be a hydration mismatch.
 */
export const returningVisitorStore = {
  subscribe: () => () => {},
  getSnapshot: hasReturningCookie,
  getServerSnapshot: () => false,
};
