"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { motion } from "framer-motion";
import {
  Bot,
  Brain,
  ChevronsUpDown,
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
import { TABS, type TabDef } from "@/lib/tabs";
import type { TabId, WorkspaceId } from "@/lib/types";
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

const WORKSPACES: { id: WorkspaceId; name: string; sub: string; short: string }[] = [
  { id: "mit", name: "MIT FY2025", sub: "Public report · read-only", short: "MIT" },
  { id: "sandbox", name: "Sandbox University", sub: "Synthetic · September close", short: "SU" },
];

export function AppSidebar() {
  const [open, setOpen] = useState(false);
  return (
    <Sidebar open={open} setOpen={setOpen}>
      <SidebarBody className="justify-between gap-6">
        <SidebarContent />
      </SidebarBody>
    </Sidebar>
  );
}

function SidebarContent() {
  const { open } = useSidebar();
  const { bundle } = useData();
  const pathname = usePathname();
  const pending = bundle.approvals.filter((a) => a.status === "pending").length;
  const groups = [...new Set(TABS.map((t) => t.group))];

  return (
    <div className="flex flex-1 flex-col overflow-y-auto overflow-x-hidden">
      {open ? <Logo /> : <LogoIcon />}

      <WorkspaceSwitch />

      <div className="mt-2 flex flex-col">
        {groups.map((group) => (
          <div key={group}>
            <motion.div
              animate={{
                display: open ? "block" : "none",
                opacity: open ? 1 : 0,
              }}
              className="px-2 pb-1 pt-3 text-[10px] uppercase tracking-wider text-neutral-400 whitespace-pre"
            >
              {group}
            </motion.div>
            {TABS.filter((t) => t.group === group).map((tab) => (
              <NavItem
                key={tab.id}
                tab={tab}
                active={tab.href === "/" ? pathname === "/" : pathname.startsWith(tab.href)}
                disabled={bundle.workspace.disabled_tabs.includes(tab.id)}
                badge={tab.id === "approvals" && pending > 0 ? String(pending) : tab.tag}
                badgeTone={tab.id === "approvals" && pending > 0 ? "count" : "tag"}
              />
            ))}
          </div>
        ))}
      </div>

      <div className="mt-auto pt-4">
        <SidebarLink
          link={{
            label: `${bundle.agents.length} agents · ${bundle.workspace.model}`,
            href: "/board",
            icon: <Bot className="h-5 w-5 flex-shrink-0 text-neutral-700" />,
          }}
          className="rounded-md px-2 hover:bg-neutral-200/60"
        />
        <motion.div
          animate={{ display: open ? "block" : "none", opacity: open ? 1 : 0 }}
          className="px-2 text-[10.5px] text-neutral-500 whitespace-pre"
        >
          Run budget: {bundle.workspace.run_budget.used} / {bundle.workspace.run_budget.total} tool calls
        </motion.div>
      </div>
    </div>
  );
}

function NavItem({
  tab,
  active,
  disabled,
  badge,
  badgeTone,
}: {
  tab: TabDef;
  active: boolean;
  disabled: boolean;
  badge?: string;
  badgeTone: "count" | "tag";
}) {
  const { open } = useSidebar();
  const Icon = ICON[tab.id];
  return (
    <div className="relative">
      <SidebarLink
        link={{
          label: tab.label,
          href: tab.href,
          icon: (
            <Icon
              className={cn(
                "h-5 w-5 flex-shrink-0",
                active ? "text-teal-700" : disabled ? "text-neutral-400" : "text-neutral-700",
              )}
            />
          ),
        }}
        className={cn(
          "rounded-md px-2 transition-colors hover:bg-neutral-200/60",
          active && "bg-emerald-100/80 [&_span]:!font-semibold [&_span]:!text-teal-700",
          disabled && "opacity-50 [&_span]:!text-neutral-400",
        )}
      />
      {badge && (
        <motion.span
          animate={{ display: open ? "inline-block" : "none", opacity: open ? 1 : 0 }}
          className={cn(
            "pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded-full px-1.5 text-[10px] font-bold",
            badgeTone === "count" ? "bg-teal-700 text-white" : "bg-teal-200 text-teal-800",
          )}
        >
          {badge}
        </motion.span>
      )}
      {badgeTone === "count" && badge && !open && (
        <span className="pointer-events-none absolute left-[18px] top-1.5 h-2 w-2 rounded-full bg-teal-700 ring-2 ring-neutral-100" />
      )}
      {disabled && (
        <motion.span
          animate={{ display: open ? "inline-block" : "none", opacity: open ? 1 : 0 }}
          className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[11px] text-neutral-400"
          title="Not available for public reports"
        >
          ⊘
        </motion.span>
      )}
    </div>
  );
}

function WorkspaceSwitch() {
  const { open } = useSidebar();
  const { ws, setWs } = useData();
  const [menu, setMenu] = useState(false);
  const current = WORKSPACES.find((w) => w.id === ws)!;

  return (
    <div className="relative mt-4">
      <button
        type="button"
        disabled={!open}
        onClick={() => setMenu((m) => !m)}
        className="flex w-full items-center justify-start gap-2 rounded-md py-1 text-left disabled:cursor-default"
      >
        <span className="grid h-7 w-7 flex-shrink-0 place-items-center rounded-md bg-teal-700 text-[10px] font-bold text-white">
          {current.short}
        </span>
        <motion.span
          animate={{ display: open ? "inline-block" : "none", opacity: open ? 1 : 0 }}
          className="min-w-0 flex-1 whitespace-pre text-sm"
        >
          <span className="block truncate font-medium text-neutral-800">{current.name}</span>
          <span className="block truncate text-[10.5px] text-neutral-500">{current.sub}</span>
        </motion.span>
        <motion.span animate={{ display: open ? "inline-block" : "none", opacity: open ? 1 : 0 }}>
          <ChevronsUpDown className="h-4 w-4 flex-shrink-0 text-neutral-400" />
        </motion.span>
      </button>

      {open && menu && (
        <div className="absolute inset-x-0 top-full z-30 mt-1 overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-lg">
          {WORKSPACES.map((w) => (
            <button
              key={w.id}
              type="button"
              onClick={() => {
                setWs(w.id);
                setMenu(false);
              }}
              className={cn(
                "block w-full px-2.5 py-2 text-left text-xs hover:bg-neutral-50",
                w.id === ws && "bg-teal-50",
              )}
            >
              <b className="font-semibold">{w.name}</b>
              <small className="block text-neutral-500">{w.sub}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export const Logo = () => {
  return (
    <Link
      href="/"
      className="relative z-20 flex items-center space-x-2 py-1 text-sm font-normal text-black"
    >
      <div className="h-5 w-6 flex-shrink-0 rounded-br-lg rounded-tr-sm rounded-tl-lg rounded-bl-sm bg-gradient-to-br from-teal-700 to-teal-500" />
      <motion.span
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="whitespace-pre font-medium text-black"
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
      className="relative z-20 flex items-center space-x-2 py-1 text-sm font-normal text-black"
    >
      <div className="h-5 w-6 flex-shrink-0 rounded-br-lg rounded-tr-sm rounded-tl-lg rounded-bl-sm bg-gradient-to-br from-teal-700 to-teal-500" />
    </Link>
  );
};
