import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronRight, Dumbbell, Plus, Search } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { EmptyState, PageHeader } from "@/components/AppShell";
import { ExerciseForm } from "@/components/ExerciseForm";
import { ExerciseImage } from "@/components/ExerciseImage";
import { FilterChips } from "@/components/FilterChips";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { filterExercises, muscleGroupsOf } from "@/lib/exerciseFilter";
import { queryClient } from "@/lib/queryClient";

export default function ExercisesPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [showDisabled, setShowDisabled] = React.useState(false);
  const [createOpen, setCreateOpen] = React.useState(false);
  const exercises = useQuery({ queryKey: ["exercises", "all"], queryFn: () => api.exercises({ include_disabled: true }) });
  const equipment = useQuery({ queryKey: ["equipment"], queryFn: api.equipment });

  const search = params.get("q") ?? "";
  const muscle = params.get("muscle");
  const equipmentId = params.get("equipment") ? Number(params.get("equipment")) : null;
  const update = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const all = exercises.data ?? [];
  const visible = filterExercises(
    all.filter((e) => showDisabled || e.enabled),
    { search, muscle, equipmentId },
  );
  const create = useMutation({
    mutationFn: api.createExercise,
    onSuccess: (ex) => {
      void queryClient.invalidateQueries({ queryKey: ["exercises"] });
      setCreateOpen(false);
      navigate(`/exercises/${ex.id}`);
    },
  });

  return (
    <div>
      <PageHeader
        title="Exercises"
        subtitle={`${all.filter((e) => e.enabled).length} in your library`}
        action={
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus /> Custom
          </Button>
        }
      />
      <div className="space-y-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-[18px] -translate-y-1/2 text-subtle" />
          <Input placeholder="Search by name, muscle or equipment" value={search} onChange={(e) => update("q", e.target.value)} className="pl-10" aria-label="Search exercises" />
        </div>
        <FilterChips
          options={muscleGroupsOf(all).map((m) => ({ value: m, label: m }))}
          value={muscle}
          onChange={(v) => update("muscle", v)}
          allLabel="All muscles"
        />
        <div className="flex items-center gap-3">
          <Select value={equipmentId ?? ""} onChange={(e) => update("equipment", e.target.value || null)} aria-label="Equipment" className="flex-1">
            <option value="">All equipment</option>
            {equipment.data?.map((eq) => (
              <option key={eq.id} value={eq.id}>
                {eq.name}
              </option>
            ))}
          </Select>
          <label className="flex shrink-0 items-center gap-2 text-sm text-muted-foreground">
            <Switch checked={showDisabled} onCheckedChange={setShowDisabled} aria-label="Show disabled exercises" />
            Disabled
          </label>
        </div>
      </div>

      <div className="mt-4">
        {exercises.isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        ) : !visible.length ? (
          <EmptyState icon={Dumbbell} title="No exercises match">
            Try a different search or filter.
          </EmptyState>
        ) : (
          <>
            <p className="mb-2 text-sm text-muted-foreground">{visible.length} shown</p>
            <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
              {visible.map((ex) => (
                <li key={ex.id}>
                  <Link
                    to={`/exercises/${ex.id}`}
                    className="flex items-center gap-3 rounded-2xl border border-border bg-card p-2.5 pr-3 transition-colors hover:bg-elevated"
                  >
                    <ExerciseImage thumbUrl={ex.thumb_url} imageUrl={ex.image_url} alt={ex.name} className="size-14 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className={ex.enabled ? "truncate font-medium" : "truncate font-medium text-muted-foreground line-through"}>{ex.name}</div>
                      <div className="truncate text-sm text-muted-foreground">
                        {[ex.primary_muscle_group, ex.equipment_detail].filter(Boolean).join(" · ")}
                      </div>
                      {(ex.scheduled_in.length > 0 || ex.is_custom) && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {ex.scheduled_in.map((t) => (
                            <Badge key={t} variant="primary">
                              {t}
                            </Badge>
                          ))}
                          {ex.is_custom && <Badge variant="info">Custom</Badge>}
                        </div>
                      )}
                    </div>
                    <ChevronRight className="size-5 shrink-0 text-subtle" />
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent title="Custom exercise" description="Add an exercise that isn't in the library.">
          <ExerciseForm submitLabel="Create exercise" onSubmit={(body) => create.mutateAsync(body)} />
        </DialogContent>
      </Dialog>
    </div>
  );
}
