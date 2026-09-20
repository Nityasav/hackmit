"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";

/**
 * The app's dropdown. Motion is taken unchanged from the emerald-ui animated dropdown:
 * the chevron turns 180° over 0.2s easeInOut, the panel enters from opacity 0 / y -10 /
 * scale 0.95 over 0.2s easeOut, and its rows stagger in 0.03s apart from x -20.
 *
 * It replaces a native <select>, so it carries what a select carries and the original did
 * not: a value, a change handler, a disabled state, a `name` for forms read through
 * FormData, and keyboard operation. Colours and type come from our tokens rather than the
 * original's slate/zinc.
 */

export interface DropdownOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface AnimatedDropdownProps {
  options: DropdownOption[];
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  /** Renders a hidden input so forms reading FormData still see this field. */
  name?: string;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  buttonClassName?: string;
  "aria-label"?: string;
}

function useClickOutside(ref: React.RefObject<HTMLElement | null>, handler: () => void) {
  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) handler();
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [ref, handler]);
}

export function AnimatedDropdown({
  options,
  value,
  defaultValue,
  onChange,
  name,
  placeholder = "Choose…",
  disabled,
  className,
  buttonClassName,
  "aria-label": ariaLabel,
}: AnimatedDropdownProps) {
  const [open, setOpen] = useState(false);
  // Uncontrolled when no `value` is passed, so a form-only dropdown still shows its choice.
  const [internal, setInternal] = useState(defaultValue ?? "");
  const [active, setActive] = useState(0);
  const wrapper = useRef<HTMLDivElement>(null);
  const listId = useId();

  const selected = value !== undefined ? value : internal;
  const current = options.find((option) => option.value === selected);

  useClickOutside(wrapper, () => setOpen(false));

  const choose = (option: DropdownOption) => {
    if (option.disabled) return;
    if (value === undefined) setInternal(option.value);
    onChange?.(option.value);
    setOpen(false);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (disabled) return;
    if (event.key === "Escape") return setOpen(false);
    if (!open && (event.key === "Enter" || event.key === " " || event.key === "ArrowDown")) {
      event.preventDefault();
      setActive(Math.max(0, options.findIndex((option) => option.value === selected)));
      return setOpen(true);
    }
    if (!open) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((index) => (index + step + options.length) % options.length);
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (options[active]) choose(options[active]);
    }
  };

  return (
    <div ref={wrapper} data-state={open ? "open" : "closed"} className={cn("relative inline-block", className)}>
      {name && <input type="hidden" name={name} value={selected} />}
      <button
        type="button"
        disabled={disabled}
        // A button's implicit role does not take aria-activedescendant, so the active option went
        // unannounced. The combobox role is the one that carries it, and it is what a collapsed
        // select-like control is meant to be.
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        // Without this the highlighted row is visible but unannounced: a screen reader follows
        // focus, which stays on the trigger while the arrow keys move through the list.
        aria-activedescendant={open && options[active] ? `${listId}-${active}` : undefined}
        aria-label={ariaLabel}
        onClick={() => setOpen((was) => !was)}
        onKeyDown={onKeyDown}
        className={cn(
          "inline-flex w-full items-center justify-between gap-2 border border-line bg-white px-3 py-2 text-left text-sm text-ink",
          "transition-colors hover:border-ink-faint disabled:cursor-not-allowed disabled:opacity-40",
          buttonClassName,
        )}
      >
        <span className={cn("truncate", !current && "text-ink-dim")}>{current?.label ?? placeholder}</span>
        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.2, ease: "easeInOut" }}
          className="flex-none"
        >
          <ChevronDown className="h-4 w-4 text-ink-dim" aria-hidden />
        </motion.span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            id={listId}
            role="listbox"
            aria-label={ariaLabel}
            initial={{ opacity: 0, y: -10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className={cn(
              "absolute top-[calc(100%+0.5rem)] left-1/2 z-50 w-fit min-w-full -translate-x-1/2",
              "overflow-hidden rounded-md border-2 border-line bg-surface shadow-lg",
            )}
          >
            <motion.div
              initial="hidden"
              animate="visible"
              variants={{ visible: { transition: { staggerChildren: 0.03 } } }}
              // Column mappings run to dozens of options; without a cap the panel leaves the
              // viewport and the last rows cannot be reached.
              className="max-h-72 overflow-y-auto"
            >
              {options.map((option, index) => (
                <motion.button
                  key={option.value}
                  id={`${listId}-${index}`}
                  type="button"
                  role="option"
                  aria-selected={option.value === selected}
                  disabled={option.disabled}
                  onClick={() => choose(option)}
                  onMouseEnter={() => setActive(index)}
                  variants={{ hidden: { opacity: 0, x: -20 }, visible: { opacity: 1, x: 0 } }}
                  className={cn(
                    "inline-block w-full px-3 py-2 text-left text-sm text-ink",
                    "border-b-2 border-line last:border-b-0",
                    "bg-surface transition-colors duration-150 hover:bg-surface-2",
                    option.value === selected && "font-semibold",
                    index === active && "bg-surface-2",
                    option.disabled && "cursor-not-allowed opacity-40",
                  )}
                >
                  {option.label}
                </motion.button>
              ))}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default AnimatedDropdown;
