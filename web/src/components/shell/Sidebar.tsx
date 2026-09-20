"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Bot,
  Brain,
  FileSearch,
  FileText,
  LayoutDashboard,
  type LucideIcon,
  ScrollText,
  SquareKanban,
  Stamp,
  Workflow,
} from "lucide-react";
import { Sidebar, SidebarBody, SidebarLink, useSidebar } from "@/components/ui/sidebar";
import { useData } from "@/lib/data";
import { TABS } from "@/lib/tabs";
import type { TabId } from "@/lib/types";
import { cn } from "@/lib/utils";

const ICON: Record<TabId, LucideIcon> = {
  command: LayoutDashboard,
  board: SquareKanban,
  workflows: Workflow,
  findings: FileSearch,
  approvals: Stamp,
  reports: FileText,
  reasoning: ScrollText,
  learning: Brain,
};

export function AppSidebar() {
  const [open, setOpen] = useState(false);

  // Keeps `open` true only while the cursor is actually over the rail. The component's
  // own onMouseEnter/onMouseLeave still run; this just guarantees the exit, because the
  // rail animates its own width under the cursor and a fast move can outrun the event.
  useEffect(() => {
    const onPointerMove = (e: PointerEvent) => {
      const rail = document.querySelector<HTMLElement>("[data-sidebar-rail]");
      if (!rail) return;
      const box = rail.getBoundingClientRect();
      if (box.width === 0) return;
      setOpen(
        e.clientX >= box.left && e.clientX <= box.right && e.clientY >= box.top && e.clientY <= box.bottom,
      );
    };
    const close = () => setOpen(false);

    window.addEventListener("pointermove", onPointerMove, { passive: true });
    window.addEventListener("blur", close);
    document.addEventListener("pointerleave", close);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("blur", close);
      document.removeEventListener("pointerleave", close);
    };
  }, []);

  return (
    <Sidebar open={open} setOpen={setOpen}>
      <SidebarBody data-sidebar-rail className="justify-between gap-10">
        <SidebarContent />
      </SidebarBody>
    </Sidebar>
  );
}

function SidebarContent() {
  const { open, setOpen } = useSidebar();
  const { bundle, ws, setWs, intakeWorkspaces } = useData();
  const pathname = usePathname();
  const router = useRouter();
  const pending = bundle.approvals.filter((a) => a.status === "pending").length;

  // Keep recorded examples clearly separate from workspaces created through intake.
  const workspaces = [
    { id: "sandbox", name: "Sandbox University", short: "SU" },
    { id: "mit", name: "MIT FY2025", short: "MIT" },
    ...intakeWorkspaces.map((w) => ({ id: w.id, name: w.name, short: initials(w.name) })),
  ];
  const current = workspaces.find((workspace) => workspace.id === ws) ?? { id: ws, name: bundle.workspace.name, short: initials(bundle.workspace.name) };

  const links = TABS.map((tab) => ({
    id: tab.id,
    label: tab.label,
    href: tab.href,
    icon: <NavIcon tab={tab.id} active={isActive(pathname, tab.href)} />,
    active: isActive(pathname, tab.href),
    disabled: bundle.workspace.disabled_tabs.includes(tab.id),
    badge: tab.id === "approvals" && pending > 0 ? String(pending) : tab.tag,
  }));

  return (
    <>
      <div className="flex flex-1 flex-col overflow-y-auto overflow-x-hidden">
        {open ? <Logo /> : <LogoIcon />}

        <div className="mt-4">
          {!open ? (
            <button type="button" onClick={() => setOpen(true)} className="grid w-full place-items-center py-2 hover:bg-surface-3" aria-label={`Choose workspace. Current: ${current.name}`} title={`Choose workspace · ${current.name}`}>
              <span className="grid h-7 w-7 place-items-center bg-ink text-[12px] font-bold text-white">{current.short}</span>
            </button>
          ) : (
            <label className="block px-2 text-[11px] font-semibold uppercase tracking-wide text-ink-dim">
              Workspace
              <select
                aria-label="Current workspace"
                value={ws}
                onChange={(event) => {
                  const next = event.target.value;
                  if (next === "__new") {
                    router.push("/#new-institution");
                    window.dispatchEvent(new Event("schooltrace:new-institution"));
                  } else {
                    setWs(next);
                    router.push("/");
                  }
                  setOpen(false);
                }}
                className="mt-1 w-full border border-line bg-surface px-2 py-2 text-[12px] normal-case tracking-normal text-ink"
              >
                <optgroup label="Recorded examples">
                  <option value="sandbox">Sandbox University · recorded</option>
                  <option value="mit">MIT FY2025 · recorded</option>
                </optgroup>
                {intakeWorkspaces.length > 0 && <optgroup label="Institution workspaces">
                  {intakeWorkspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
                </optgroup>}
                <option value="__new">＋ Create new institution…</option>
              </select>
            </label>
          )}
        </div>

        <div className="mt-8 flex flex-col gap-2">
          {links.map((link) => (
            <div key={link.id} className="relative">
              <SidebarLink
                link={link}
                className={cn(
                  "rounded-md transition-colors hover:bg-surface-3",
                  open ? "px-2" : "justify-center px-0",
                  link.active && "bg-surface-3 [&_span]:!font-semibold [&_span]:!text-ink",
                  link.disabled && "opacity-50",
                )}
              />
              {link.badge && (
                <motion.span
                  animate={{ display: open ? "inline-block" : "none", opacity: open ? 1 : 0 }}
                  className={cn(
                    "pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded-none px-1.5 text-[12px] font-bold",
                    link.id === "approvals" ? "bg-ink text-white" : "bg-surface-3 text-ink-dim",
                  )}
                >
                  {link.badge}
                </motion.span>
              )}
              {link.id === "approvals" && pending > 0 && !open && (
                <span className="pointer-events-none absolute left-1/2 top-0.5 ml-[7px] h-2 w-2 rounded-none bg-ink ring-2 ring-surface-2" />
              )}
            </div>
          ))}
        </div>
      </div>

      <div>
        <SidebarLink
          link={{
            label: `${bundle.agents.length} agents · ${bundle.workspace.model}`,
            href: "/board",
            icon: <Bot className="h-7 w-7 flex-shrink-0 rounded-none p-1 text-ink-dim" />,
          }}
        />
      </div>
    </>
  );
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
}

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function NavIcon({ tab, active }: { tab: TabId; active: boolean }) {
  const Icon = ICON[tab];
  return <Icon className={cn("h-5 w-5 flex-shrink-0", active ? "text-ink" : "text-ink-dim")} />;
}

export const Logo = () => {
  return (
    <Link
      href="/"
      className="relative z-20 flex items-center space-x-2 py-1 text-sm font-normal text-ink"
    >
      <div className="h-5 w-6 flex-shrink-0     bg-gradient-to-br from-ink to-ink-dim" />
      <motion.span
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="whitespace-pre font-medium text-ink"
      >
        SchoolTrace
      </motion.span>
    </Link>
  );
};

export const LogoIcon = () => {
  return (
    <Link
      href="/"
      className="relative z-20 flex items-center space-x-2 py-1 text-sm font-normal text-ink"
    >
      <div className="h-5 w-6 flex-shrink-0     bg-gradient-to-br from-ink to-ink-dim" />
    </Link>
  );
};
