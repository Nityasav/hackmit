"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, useSyncExternalStore } from "react";

import { getSupabaseClient } from "@/lib/supabase/client";
import { markReturningVisitor, returningVisitorStore } from "@/lib/session-cookie";
import { track } from "@/lib/activity";

type Mode = "signin" | "signup";

function AuthForm() {
  const supabase = getSupabaseClient();
  const returning = useSyncExternalStore(
    returningVisitorStore.subscribe,
    returningVisitorStore.getSnapshot,
    returningVisitorStore.getServerSnapshot,
  );
  const router = useRouter();
  const params = useSearchParams();
  // Only ever redirect within this site. A bare "/..." path is fine; anything
  // absolute or protocol-relative ("//evil.com") would send the user off-site.
  const requested = params.get("next");
  const next = requested && requested.startsWith("/") && !requested.startsWith("//") ? requested : "/";

  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");

    try {
      if (mode === "signup") {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: { data: { full_name: fullName } },
        });
        if (error) throw error;

        // signUp only returns a session when the project has confirmation
        // switched off. The database confirms the address on insert, so sign
        // in straight away and land the new account in the dashboard.
        if (!data.session) {
          const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
          if (signInError) {
            setNotice("Account created. Check your email to confirm it, then sign in.");
            setMode("signin");
            return;
          }
        }
      } else {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        if (error) throw error;
      }

      markReturningVisitor();
      void track(mode === "signup" ? "sign_up" : "sign_in");

      // Full reload so the proxy re-reads the session cookie it just set.
      router.push(next);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const field = "w-full border border-line bg-surface px-3 py-2.5 text-[14px] outline-none focus:border-ink";

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-6">
      <div className="w-full max-w-[400px]">
        <h1 className="text-2xl font-bold tracking-tight">SchoolTrace</h1>
        <p className="mt-2 font-accent text-[14px] text-ink-dim">
          {returning
            ? "Welcome back. Sign in to pick up where you left off."
            : "An Office of the CFO for schools, run by AI agents."}
        </p>

        <div className="mt-8 flex border-b border-line">
          {(["signin", "signup"] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMode(m);
                setError("");
                setNotice("");
              }}
              className={`-mb-px cursor-pointer border-b-2 px-4 py-2 text-[14px] font-semibold transition-colors ${
                mode === m ? "border-ink text-ink" : "border-transparent text-ink-dim hover:text-ink"
              }`}
            >
              {m === "signin" ? "Sign in" : "Create account"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="mt-6 flex flex-col gap-4">
          {mode === "signup" && (
            <label className="flex flex-col gap-1.5">
              <span className="text-[13px] font-semibold">Name</span>
              <input
                className={field}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                autoComplete="name"
                placeholder="Alex Rivera"
              />
            </label>
          )}

          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Email</span>
            <input
              className={field}
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              placeholder="you@school.edu"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] font-semibold">Password</span>
            <input
              className={field}
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              placeholder="At least 6 characters"
            />
          </label>

          {error && (
            <p role="alert" className="border border-red-300 bg-red-50 px-3 py-2 text-[13px] text-red-800">
              {error}
            </p>
          )}
          {notice && (
            <p role="status" className="border border-line bg-surface-2 px-3 py-2 text-[13px] text-ink">
              {notice}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="mt-2 cursor-pointer bg-ink px-4 py-3 text-[14px] font-semibold text-white transition-colors hover:bg-ink-dim disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Working…" : mode === "signin" ? "Sign in" : "Create account"}
          </button>
        </form>

        <p className="mt-6 font-accent text-[13px] text-ink-dim">
          {mode === "signin" ? "No account yet? " : "Already have one? "}
          <button
            type="button"
            className="cursor-pointer font-semibold text-ink underline"
            onClick={() => {
              setMode(mode === "signin" ? "signup" : "signin");
              setError("");
              setNotice("");
            }}
          >
            {mode === "signin" ? "Create one" : "Sign in"}
          </button>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <AuthForm />
    </Suspense>
  );
}
