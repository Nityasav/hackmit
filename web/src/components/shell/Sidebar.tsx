"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Bot,
  Brain,
  FileSearch,
  FileText,
  LayoutDashboard,
  LogOut,
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

export function AppSidebar({ userEmail }: { userEmail: string }) {
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
        <SidebarContent userEmail={userEmail} />
      </SidebarBody>
    </Sidebar>
  );
}

function SidebarContent({ userEmail }: { userEmail: string }) {
  const { open } = useSidebar();
  const { bundle, ws, setWs, intakeWorkspaces } = useData();
  const pathname = usePathname();
  const pending = bundle.approvals.filter((a) => a.status === "pending").length;

  // Demo workspaces plus anything imported through intake. Clicking cycles through them.
  const workspaces = [
    { id: "sandbox", name: "Sandbox University", short: "SU" },
    { id: "mit", name: "MIT FY2025", short: "MIT" },
    ...intakeWorkspaces.map((w) => ({ id: w.id, name: w.name, short: initials(w.name) })),
  ];
  const currentIndex = Math.max(
    0,
    workspaces.findIndex((w) => w.id === ws),
  );
  const current = workspaces[currentIndex] ?? { name: bundle.workspace.name, short: initials(bundle.workspace.name) };
  const nextWorkspace = workspaces[(currentIndex + 1) % workspaces.length];

  const links = TABS.map((tab) => ({
    id: tab.id,
    label: tab.label,
    href: tab.href,
    icon: <NavIcon tab={tab.id} active={isActive(pathname, tab.href)} />,
    active: isActive(pathname, tab.href),
    disabled: bundle.workspace.disabled_tabs.includes(tab.id) && !(bundle.workspace.intake && ["approvals", "workflows", "learning"].includes(tab.id)),
    badge: tab.id === "approvals" && pending > 0 ? String(pending) : tab.tag,
  }));

  return (
    <>
      <div className="flex flex-1 flex-col overflow-y-auto overflow-x-hidden">
        {open ? <Logo /> : <LogoIcon />}

        {/* Same markup as SidebarLink, as a button: it switches workspace instead of navigating. */}
        <button
          type="button"
          onClick={() => setWs(nextWorkspace.id)}
          title={`Switch to ${nextWorkspace.name}`}
          className={cn("group/sidebar mt-4 flex items-center gap-2 rounded-md py-2 hover:bg-surface-3", open ? "justify-start px-2" : "justify-center px-0")}
        >
          <span className="grid h-7 w-7 flex-shrink-0 place-items-center rounded-md bg-ink text-[12px] font-bold text-white">
            {current.short}
          </span>
          <motion.span
            animate={{ display: open ? "inline-block" : "none", opacity: open ? 1 : 0 }}
            className="m-0! inline-block whitespace-pre p-0! text-sm text-ink-dim transition duration-150 group-hover/sidebar:translate-x-1"
          >
            {current.name}
          </motion.span>
        </button>

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

      <div className="flex flex-col gap-1">
        <SidebarLink
          link={{
            label: bundle.workspace.intake ? "Five-agent review & activity" : `${bundle.agents.length} agents · ${bundle.workspace.model}`,
            href: bundle.workspace.intake ? "/cfo" : "/board",
            icon: <Bot className="h-7 w-7 flex-shrink-0 rounded-none p-1 text-ink-dim" />,
          }}
        />

        <form action="/auth/signout" method="post">
          <button
            type="submit"
            title={`Sign out ${userEmail}`}
            className={cn(
              "group/sidebar flex w-full cursor-pointer items-center gap-2 py-2 transition-colors hover:bg-surface-3",
              open ? "justify-start px-2" : "justify-center px-0",
            )}
          >
            <LogOut className="h-7 w-7 flex-shrink-0 p-1 text-ink-dim" />
            <motion.span
              animate={{ display: open ? "inline-block" : "none", opacity: open ? 1 : 0 }}
              className="min-w-0 truncate text-sm text-ink-dim transition duration-150 group-hover/sidebar:translate-x-1"
            >
              Sign out
            </motion.span>
          </button>
        </form>

        <motion.div
          animate={{ display: open ? "block" : "none", opacity: open ? 1 : 0 }}
          className="truncate px-2 pb-1 font-accent text-[12px] text-ink-faint"
          title={userEmail}
        >
          {userEmail}
        </motion.div>
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
