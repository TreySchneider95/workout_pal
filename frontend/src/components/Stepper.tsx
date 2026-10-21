import { Minus, Plus } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

interface StepperProps {
  value: number | null;
  onChange: (value: number) => void;
  /** Explicit list of allowed values (e.g. the dumbbells you own). */
  options?: number[] | null;
  step?: number;
  min?: number;
  max?: number;
  unit?: string;
  label: string;
  format?: (value: number | null) => string;
  decimals?: boolean;
  dim?: boolean;
  /** Narrower -/+ buttons for tight layouts. */
  compact?: boolean;
  className?: string;
}

export function nextValue(value: number | null, dir: 1 | -1, options: number[] | null | undefined, step: number, min: number, max: number): number {
  const current = value ?? (dir > 0 ? min - step : min + step);
  if (options && options.length) {
    const sorted = [...options].sort((a, b) => a - b);
    if (dir > 0) return sorted.find((o) => o > current + 1e-9) ?? sorted[sorted.length - 1];
    return [...sorted].reverse().find((o) => o < current - 1e-9) ?? sorted[0];
  }
  const next = Math.round((current + dir * step) * 100) / 100;
  return Math.min(max, Math.max(min, next));
}

/** Large -/+ control. Tap the number to type a value. */
export function Stepper({
  value,
  onChange,
  options,
  step = 1,
  min = 0,
  max = 1000,
  unit,
  label,
  format,
  decimals = false,
  dim = false,
  compact = false,
  className,
}: StepperProps) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState("");

  const commit = () => {
    setEditing(false);
    const parsed = decimals ? parseFloat(draft) : parseInt(draft, 10);
    if (!Number.isNaN(parsed)) onChange(Math.min(max, Math.max(min, parsed)));
  };

  const display = format ? format(value) : value === null ? "–" : String(value);

  return (
    <div className={cn("flex h-12 min-w-0 items-stretch overflow-hidden rounded-xl border border-border bg-background", className)}>
      <button
        type="button"
        className={cn("flex shrink-0 items-center justify-center text-muted-foreground transition-colors hover:text-foreground active:bg-muted", compact ? "w-8" : "w-10")}
        onClick={() => onChange(nextValue(value, -1, options, step, min, max))}
        aria-label={`Decrease ${label}`}
      >
        <Minus className="size-[18px]" />
      </button>
      {editing ? (
        <input
          autoFocus
          type="number"
          inputMode={decimals ? "decimal" : "numeric"}
          className="tabular w-full min-w-0 bg-transparent text-center text-lg font-semibold outline-none"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") (e.target as HTMLInputElement).blur();
            if (e.key === "Escape") setEditing(false);
          }}
          aria-label={label}
        />
      ) : (
        <button
          type="button"
          className="flex min-w-0 flex-1 flex-col items-center justify-center leading-none"
          onClick={() => {
            setDraft(value === null ? "" : String(value));
            setEditing(true);
          }}
          aria-label={`${label}: ${display}${unit ? ` ${unit}` : ""}. Tap to type.`}
        >
          <span className={cn("tabular truncate text-lg font-semibold", dim && "text-muted-foreground")}>{display}</span>
          {unit && <span className="mt-0.5 text-[10px] font-medium uppercase tracking-wide text-subtle">{unit}</span>}
        </button>
      )}
      <button
        type="button"
        className={cn("flex shrink-0 items-center justify-center text-muted-foreground transition-colors hover:text-foreground active:bg-muted", compact ? "w-8" : "w-10")}
        onClick={() => onChange(nextValue(value, 1, options, step, min, max))}
        aria-label={`Increase ${label}`}
      >
        <Plus className="size-[18px]" />
      </button>
    </div>
  );
}
