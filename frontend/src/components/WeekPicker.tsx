import { cn } from "@/lib/utils";

/**
 * Which plan weeks a workout runs in. `null` means every week (all chips on).
 * Toggling a week never leaves the workout with no weeks.
 */
export function WeekPicker({
  planWeeks,
  value,
  onChange,
  disabled,
}: {
  planWeeks: number;
  value: number[] | null;
  onChange: (weeks: number[] | null) => void;
  disabled?: boolean;
}) {
  const all = Array.from({ length: planWeeks }, (_, i) => i + 1);
  const selected = value ?? all;
  const toggle = (week: number) => {
    const next = selected.includes(week) ? selected.filter((w) => w !== week) : [...selected, week].sort((a, b) => a - b);
    if (!next.length) return;
    onChange(next.length === planWeeks ? null : next);
  };
  const chip = (active: boolean) =>
    cn(
      "h-9 min-w-9 shrink-0 rounded-full border px-3 text-sm font-medium transition-colors disabled:opacity-50",
      active ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground",
    );
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Plan weeks">
      <button type="button" className={chip(value === null)} disabled={disabled} onClick={() => onChange(null)}>
        Every week
      </button>
      {all.map((w) => (
        <button
          key={w}
          type="button"
          className={chip(selected.includes(w))}
          disabled={disabled}
          aria-pressed={selected.includes(w)}
          aria-label={`Week ${w}`}
          onClick={() => toggle(w)}
        >
          {w}
        </button>
      ))}
    </div>
  );
}
