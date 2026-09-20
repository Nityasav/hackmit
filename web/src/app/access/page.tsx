"use client";
import { useEffect, useState } from "react";
import { intakeApi, useData } from "@/lib/data";
type Access = { authentication_configured: boolean; user: { name: string; role: string; mode: string } | null; retention: string };
export default function AccessPage() {
  const { ws, refreshWorkspaces } = useData();
  const [access, setAccess] = useState<Access | null>(null);
  const [username, setUsername] = useState(""); const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState(""); const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { intakeApi<Access>("/api/access/status").then(setAccess).catch(e => setMessage(e.message)); }, []);
  async function login(e: React.FormEvent) {
    e.preventDefault(); setBusy(true);
    try { await intakeApi("/api/access/login", { method: "POST", body: { username, password } }); setPassword(""); window.location.reload(); }
    catch (e) { setMessage(e instanceof Error ? e.message : "Sign-in failed"); } finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true);
    try { await intakeApi(`/api/workspaces/${ws}`, { method: "DELETE", body: { confirmation } }); await refreshWorkspaces(); setConfirmation(""); setMessage("Workspace logically deleted, including original uploads, reviews and follow-up. OS backups and filesystem remnants are not erased."); }
    catch (e) { setMessage(e instanceof Error ? e.message : "Deletion failed"); } finally { setBusy(false); }
  }
  return <div className="mx-auto max-w-3xl space-y-6"><h1 className="text-3xl font-semibold">Access, privacy &amp; limits</h1><section className="border border-line p-5"><h2 className="text-xl font-semibold">Laptop-only by design</h2><p className="mt-3">Use fictional or approved public records. The server refuses non-loopback connections and untrusted browser origins. This is not authorization to use confidential employee, student or school-board records.</p><p className="mt-3 text-sm text-ink-dim">Local database files have restricted permissions, not application-level encryption. Enterprise identity, managed encrypted backups, legal/privacy review and an Ontario accounting adapter remain deployment gates.</p></section>
    <section className="border border-line p-5"><h2 className="font-semibold">{access?.authentication_configured ? "Account access" : "Local demo mode — no sign-in configured"}</h2><p className="mt-2 text-sm">{access?.user ? `Current identity: ${access.user.name} · ${access.user.role}.` : "Sign in with a configured account."} Anyone using this unlocked laptop can access local demo mode. Optional accounts enforce viewer, analyst, reviewer and admin permissions plus assigned workspace access.</p>
      {access?.authentication_configured && !access.user && <form onSubmit={login} className="mt-4 space-y-3"><label className="block">Username<input autoComplete="username" className="mt-1 block w-full border border-line p-2" value={username} onChange={e => setUsername(e.target.value)} /></label><label className="block">Password<input type="password" autoComplete="current-password" className="mt-1 block w-full border border-line p-2" value={password} onChange={e => setPassword(e.target.value)} /></label><button disabled={busy} className="bg-ink px-4 py-2 text-white">Sign in</button></form>}
      {access?.user?.mode === "authenticated" && <button className="mt-3 border border-line px-4 py-2" onClick={async () => { await intakeApi("/api/access/logout", { method: "POST" }); window.location.reload(); }}>Sign out</button>}</section>
    <section className="border border-line p-5"><h2 className="font-semibold">What leaves this laptop?</h2><p className="mt-2">Record checks do not call a model. Starting a live agent investigation sends selected source excerpts and financial records to the configured API provider. Keys stay on the server. Choose the records deliberately; do not use the live option with confidential data.</p></section>
    <section className="border border-red-200 p-5"><h2 className="font-semibold">Retention & workspace deletion</h2><p className="mt-2 text-sm">{access?.retention}</p><p className="mt-3 text-sm">An admin may delete the selected uploaded workspace and its original files, snapshots, scans, model runs and follow-up history. This cannot be undone in the app. Export a report first if needed.</p>
      {ws.startsWith("ws-") && access?.user?.role === "admin" ? <><label className="mt-3 block text-sm">Type <b>{ws}</b> to confirm<input aria-label="Workspace deletion confirmation" value={confirmation} onChange={e => setConfirmation(e.target.value)} className="mt-2 block w-full border border-line p-2" /></label><button disabled={busy || confirmation !== ws} onClick={() => void remove()} className="mt-3 bg-red-800 px-4 py-2 text-white disabled:opacity-40">Delete this workspace and its records</button></> : <p className="mt-3 text-sm">Select a school you added, as an admin, to delete it.</p>}</section>
    {message && <p role="status" className="border border-line p-3">{message}</p>}
  </div>;
}
