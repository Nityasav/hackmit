"use client";

import { useId, useState } from "react";
import { ChevronDown } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * The expanding sections — "Committed sources (24)", "What changed?" — in the same motion
 * language as AnimatedDropdown: the chevron turns 180° over 0.2s easeInOut and the panel
 * arrives from opacity 0 / y -10 / scale 0.95 over 0.2s easeOut.
 *
 * It replaces <details>/<summary>, so it keeps a native disclosure's behaviour: collapsed by
 * default unless told otherwise, the summary is the only control, and the content is labelled
 * by it. Height is animated alongside the entrance because this content sits in the page flow
 * rather than floating over it — a panel that faded in at full height would jump the layout.
 */

interface AnimatedDisclosureProps {
  summary: React.ReactNode;
  children: React.ReactNode;
  defaultOpen?: boolean;
  className?: string;
  summaryClassName?: string;
  contentClassName?: string;
}

export function AnimatedDisclosure({
  summary,
  children,
  defaultOpen = false,
  className,
  summaryClassName,
  contentClassName,
}: AnimatedDisclosureProps) {
  const [open, setOpen] = useState(defaultOpen);
  // Clipping is needed while the height animates and harmful afterwards: a dropdown opened inside
  // a section would have its popup cut off by the clipping box for as long as the section stayed
  // open. Starts true when the section opens unanimated, which is what defaultOpen does.
  const [settled, setSettled] = useState(defaultOpen);
  const id = useId();

  const toggle = () => {
    if (open) setSettled(false);
    setOpen(!open);
  };

  return (
    <div data-state={open ? "open" : "closed"} className={className}>
      <button
        type="button"
        aria-expanded={open}
        // Only while the region exists: closed content is unmounted, and pointing at a missing id
        // is an ARIA violation rather than a harmless leftover.
        aria-controls={open ? `${id}-content` : undefined}
        onClick={toggle}
        className={cn(
          "flex w-full cursor-pointer items-center gap-2 text-left",
          summaryClassName,
        )}
      >
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.2, ease: "easeInOut" }}
          className="flex-none"
        >
          <ChevronDown className="h-4 w-4 text-ink-dim" aria-hidden />
        </motion.span>
        <span className="min-w-0 flex-1">{summary}</span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={`${id}-content`}
            role="region"
            initial={{ opacity: 0, y: -10, scale: 0.95, height: 0 }}
            animate={{ opacity: 1, y: 0, scale: 1, height: "auto" }}
            // The clip is restated here rather than left to the class: AnimatePresence renders the
            // leaving element with the props it had while open, so a settled section would collapse
            // unclipped and spill its content over what sits below it. An inline style beats the
            // frozen class.
            exit={{ opacity: 0, y: -10, scale: 0.95, height: 0, overflow: "hidden" }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            // This fires for the exit animation too, and the clip has to be back before the next
            // expansion or the content spills while the height animates. Reading which animation
            // finished is what works here: AnimatePresence renders the leaving element with the
            // props it had while open, so a `open === true` guard is still true on the way out.
            onAnimationComplete={(finished) => {
              setSettled((finished as { height?: number | string })?.height === "auto");
            }}
            className={settled ? "overflow-visible" : "overflow-hidden"}
          >
            <div className={cn("pt-2", contentClassName)}>{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default AnimatedDisclosure;
