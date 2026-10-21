import { useQuery } from "@tanstack/react-query";
import { Check, Search } from "lucide-react";
import * as React from "react";

import { ExerciseImage } from "@/components/ExerciseImage";
import { FilterChips } from "@/components/FilterChips";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Spinner } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { filterExercises, muscleGroupsOf } from "@/lib/exerciseFilter";
import type { Exercise } from "@/lib/types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPick: (exercise: Exercise) => void | Promise<void>;
  title?: string;
  /** Exercise IDs already present (shown with a check). */
  existing?: string[];
}

/** Searchable picker over the full exercise library. */
export function ExercisePicker({ open, onOpenChange, onPick, title = "Add exercise", existing = [] }: Props) {
  const exercises = useQuery({ queryKey: ["exercises", "enabled"], queryFn: () => api.exercises(), enabled: open });
  const equipment = useQuery({ queryKey: ["equipment"], queryFn: api.equipment, enabled: open });
  const [search, setSearch] = React.useState("");
  const [muscle, setMuscle] = React.useState<string | null>(null);
  const [equipmentId, setEquipmentId] = React.useState<number | null>(null);
  const [picking, setPicking] = React.useState<string | null>(null);

  const all = exercises.data ?? [];
  const results = filterExercises(all, { search, muscle, equipmentId });
  const muscles = muscleGroupsOf(all);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} description={`${all.length} exercises in your library`} wide className="sm:h-[85dvh]">
        <div className="sticky top-0 z-10 -mx-5 space-y-2.5 bg-card px-5 pb-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 size-[18px] -translate-y-1/2 text-subtle" />
            <Input
              placeholder="Search exercises"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-10"
              aria-label="Search exercises"
            />
          </div>
          <FilterChips options={muscles.map((m) => ({ value: m, label: m }))} value={muscle} onChange={setMuscle} allLabel="All muscles" />
          <Select
            value={equipmentId ?? ""}
            onChange={(e) => setEquipmentId(e.target.value ? Number(e.target.value) : null)}
            aria-label="Equipment"
          >
            <option value="">All equipment</option>
            {equipment.data?.map((eq) => (
              <option key={eq.id} value={eq.id}>
                {eq.name}
              </option>
            ))}
          </Select>
        </div>
        {exercises.isLoading ? (
          <div className="flex justify-center py-10">
            <Spinner />
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {results.map((ex) => {
              const added = existing.includes(ex.id);
              return (
                <li key={ex.id}>
                  <button
                    className="flex w-full items-center gap-3 py-2.5 text-left transition-colors hover:bg-muted/50 disabled:opacity-50"
                    disabled={picking !== null}
                    onClick={async () => {
                      setPicking(ex.id);
                      try {
                        await onPick(ex);
                      } finally {
                        setPicking(null);
                      }
                    }}
                  >
                    <ExerciseImage thumbUrl={ex.thumb_url} imageUrl={ex.image_url} alt={ex.name} className="size-12 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{ex.name}</div>
                      <div className="truncate text-sm text-muted-foreground">
                        {[ex.primary_muscle_group, ex.equipment_detail].filter(Boolean).join(" · ")}
                      </div>
                    </div>
                    {picking === ex.id ? <Spinner /> : added && <Check className="size-5 text-primary" aria-label="Already added" />}
                  </button>
                </li>
              );
            })}
            {!results.length && <li className="py-10 text-center text-sm text-muted-foreground">No exercises match.</li>}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
