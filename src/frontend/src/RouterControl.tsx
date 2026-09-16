import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, GitBranch, LoaderCircle } from "lucide-react";
import type { RoutingMode, RoutingModeState } from "./api";

const MODES: { id: RoutingMode; label: string; description: string }[] = [
  { id: "cost", label: "Cost", description: "Cheapest model that clears a wider quality band" },
  { id: "balanced", label: "Balanced", description: "Cheapest model within ~1-2% of top quality" },
  { id: "quality", label: "Quality", description: "Highest-rated model, cost ignored" },
];

export function RouterControl({ routing, loading, busy, onChange }: {
  routing: RoutingModeState | null;
  loading: boolean;
  busy: boolean;
  onChange: (mode: RoutingMode) => void;
}) {
  const [open, setOpen] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    (menu.current?.querySelector<HTMLButtonElement>('[aria-checked="true"]')
      ?? menu.current?.querySelector<HTMLButtonElement>('[role="menuitemradio"]'))?.focus();
    function dismiss(event: PointerEvent) {
      if (event.target instanceof Node && !container.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", dismiss);
    return () => document.removeEventListener("pointerdown", dismiss);
  }, [open]);

  return (
    <div className="composer-router" ref={container}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          setOpen(false);
          trigger.current?.focus();
        }
      }}>
      <button ref={trigger} type="button" className="router-trigger"
        aria-haspopup="menu" aria-expanded={open} aria-controls="router-menu"
        aria-label={`Router: ${loading ? "loading" : routing?.mode ?? "unavailable"}${busy ? ", updating" : ""}`}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}>
        {busy || loading ? <LoaderCircle size={17} className="router-spinner" aria-hidden="true" /> : <GitBranch size={17} aria-hidden="true" />}
        Router{routing ? `: ${routing.mode}` : ""}
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && (
        <div id="router-menu" className="router-menu" role="menu" aria-label="Routing mode" ref={menu}
          onKeyDown={(event) => {
            if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            const options = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]'));
            const current = options.findIndex((option) => option === document.activeElement);
            const next = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1
              : (current + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
            options[next]?.focus();
          }}>
          {MODES.map((option) => (
            <button key={option.id} type="button" className="router-option" role="menuitemradio"
              aria-checked={routing?.mode === option.id} aria-label={option.label}
              aria-disabled={!routing?.editable || busy || loading} aria-describedby={`router-tip-${option.id}`}
              tabIndex={-1}
              onClick={() => {
                if (!routing?.editable || busy || loading) return;
                setOpen(false);
                trigger.current?.focus();
                onChange(option.id);
              }}>
              <span className="router-option-label">{option.label}<Check size={16} aria-hidden="true" /></span>
              <span id={`router-tip-${option.id}`} role="tooltip" className="router-tooltip">{option.description}</span>
            </button>
          ))}
          {(loading || !routing || !routing.editable) && (
            <p className="router-readonly" role="status">
              {loading ? "Loading routing settings..." : !routing
                ? "Routing settings unavailable. Check the backend connection and reload."
                : "Routing is read-only in this environment."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}