"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { BookOpen, FileText, Files, LogOut, type LucideIcon, Search } from "lucide-react";
import { Sidebar, SidebarBody, useSidebar } from "@/components/ui/sidebar";
import { SherlockMark } from "@/components/SherlockMark";
import { endActivitySession } from "@/lib/activity";
import { useData } from "@/lib/data";
import { NAV, type NavId } from "@/lib/tabs";
import { cn } from "@/lib/utils";

const ICON: Record<NavId, LucideIcon> = {
  books: BookOpen,
  files: Files,
  investigation: Search,
  briefing: FileText,
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

  // Every workspace is one someone created and uploaded records to. Clicking
  // cycles through them.
  const workspaces = intakeWorkspaces.map((w) => ({ id: w.id, name: w.name, short: initials(w.name) }));
  const currentIndex = Math.max(
    0,
    workspaces.findIndex((w) => w.id === ws),
  );
  const current = workspaces[currentIndex] ?? { id: ws, name: bundle.workspace.name, short: initials(bundle.workspace.name) };
  const nextWorkspace = workspaces.length ? workspaces[(currentIndex + 1) % workspaces.length] : current;

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

        <nav aria-label="Main" className="mt-8 flex flex-col gap-2">
          {NAV.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.id}
                href={item.href}
                title={item.hint}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "group/sidebar flex items-center gap-2 rounded-md py-2 transition-colors hover:bg-surface-3",
                  open ? "justify-start px-2" : "justify-center px-0",
                  active && "bg-surface-3",
                )}
              >
                <NavIcon id={item.id} active={active} />
                <motion.span
                  animate={{ display: open ? "inline-block" : "none", opacity: open ? 1 : 0 }}
                  className={cn(
                    "m-0! inline-block whitespace-pre p-0! text-sm transition duration-150 group-hover/sidebar:translate-x-1",
                    active ? "font-semibold text-ink" : "text-ink-dim",
                  )}
                >
                  {item.label}
                </motion.span>
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="flex flex-col gap-1">
        {/* The sign-out POST redirects but never unloads sessionStorage, so the
            activity session is ended here or the next person inherits it. */}
        <form action="/auth/signout" method="post" onSubmit={() => endActivitySession()}>
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

function NavIcon({ id, active }: { id: NavId; active: boolean }) {
  const Icon = ICON[id];
  return <Icon className={cn("h-5 w-5 flex-shrink-0", active ? "text-ink" : "text-ink-dim")} />;
}

export const Logo = () => {
  return (
    <Link
      href="/"
      className="relative z-20 flex items-center space-x-2 py-1 text-sm font-normal text-ink"
    >
      <SherlockMark size={28} />
      <motion.span
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="whitespace-nowrap text-xl font-semibold leading-none tracking-[-0.035em] text-ink"
      >
        Sherlock
      </motion.span>
    </Link>
  );
};

export const LogoIcon = () => {
  return (
    <Link
      href="/"
      aria-label="Sherlock home"
      className="relative z-20 flex items-center space-x-2 py-1 text-sm font-normal text-ink"
    >
      <SherlockMark size={28} />
    </Link>
  );
};
