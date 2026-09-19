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
  const { open } = useSidebar();
  const { bundle, ws, setWs } = useData();
  const pathname = usePathname();
  const pending = bundle.approvals.filter((a) => a.status === "pending").length;

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

        {/* Same markup as SidebarLink, as a button: it switches workspace instead of navigating. */}
        <button
          type="button"
          onClick={() => setWs(ws === "mit" ? "sandbox" : "mit")}
          title="Switch workspace"
          className="group/sidebar mt-4 flex items-center justify-start gap-2 rounded-md px-1 py-2 hover:bg-surface-3"
        >
          <span className="grid h-7 w-7 flex-shrink-0 place-items-center rounded-md bg-ink text-[10px] font-bold text-white">
            {ws === "mit" ? "MIT" : "SU"}
          </span>
          <motion.span
            animate={{ display: open ? "inline-block" : "none", opacity: open ? 1 : 0 }}
            className="m-0! inline-block whitespace-pre p-0! text-sm text-ink-dim transition duration-150 group-hover/sidebar:translate-x-1"
          >
            {ws === "mit" ? "MIT FY2025" : "Sandbox University"}
          </motion.span>
        </button>

        <div className="mt-8 flex flex-col gap-2">
          {links.map((link) => (
            <div key={link.id} className="relative">
              <SidebarLink
                link={link}
                className={cn(
                  "rounded-md px-2 transition-colors hover:bg-surface-3",
                  link.active && "bg-green-100 [&_span]:!font-semibold [&_span]:!text-accent-good",
                  link.disabled && "opacity-50",
                )}
              />
              {link.badge && (
                <motion.span
                  animate={{ display: open ? "inline-block" : "none", opacity: open ? 1 : 0 }}
                  className={cn(
                    "pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded-full px-1.5 text-[10px] font-bold",
                    link.id === "approvals" ? "bg-ink text-white" : "bg-green-200 text-green-800",
                  )}
                >
                  {link.badge}
                </motion.span>
              )}
              {link.id === "approvals" && pending > 0 && !open && (
                <span className="pointer-events-none absolute left-[18px] top-1 h-2 w-2 rounded-full bg-ink ring-2 ring-line" />
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
            icon: <Bot className="h-7 w-7 flex-shrink-0 rounded-full p-1 text-ink-dim" />,
          }}
        />
      </div>
    </>
  );
}

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function NavIcon({ tab, active }: { tab: TabId; active: boolean }) {
  const Icon = ICON[tab];
  return <Icon className={cn("h-5 w-5 flex-shrink-0", active ? "text-accent-good" : "text-ink-dim")} />;
}

export const Logo = () => {
  return (
    <Link
      href="/"
      className="relative z-20 flex items-center space-x-2 py-1 text-sm font-normal text-ink"
    >
      <div className="h-5 w-6 flex-shrink-0 rounded-br-lg rounded-tr-sm rounded-tl-lg rounded-bl-sm bg-gradient-to-br from-ink to-ink-dim" />
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
      <div className="h-5 w-6 flex-shrink-0 rounded-br-lg rounded-tr-sm rounded-tl-lg rounded-bl-sm bg-gradient-to-br from-ink to-ink-dim" />
    </Link>
  );
};
