import { cn } from "@/lib/utils";

export function FilterChips<T extends string | number>({
  options,
  value,
  onChange,
  allLabel = "All",
}: {
  options: { value: T; label: string }[];
  value: T | null;
  onChange: (value: T | null) => void;
  allLabel?: string;
}) {
  const chip = (active: boolean) =>
    cn(
      "h-9 shrink-0 rounded-full border px-3.5 text-sm font-medium transition-colors",
      active ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground",
    );
  return (
    <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 py-0.5 lg:mx-0 lg:flex-wrap lg:px-0">
      <button className={chip(value === null)} onClick={() => onChange(null)}>
        {allLabel}
      </button>
      {options.map((o) => (
        <button key={String(o.value)} className={chip(value === o.value)} onClick={() => onChange(value === o.value ? null : o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
