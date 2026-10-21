import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronLeft, ImagePlus, Pencil, Power } from "lucide-react";
import * as React from "react";
import { Link, useParams } from "react-router";
import { toast } from "sonner";

import { StatTile } from "@/components/AppShell";
import { BarTrend, LineTrend } from "@/components/Charts";
import { ExerciseForm } from "@/components/ExerciseForm";
import { ExerciseImage } from "@/components/ExerciseImage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { LOAD_LABEL, TRACKING_LABEL, compactNumber, dateShort, durationText, isWeighted, lb, loadLabel, num } from "@/lib/format";
import { queryClient } from "@/lib/queryClient";
import type { Exercise, ExerciseHistoryEntry } from "@/lib/types";

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-border py-2.5 text-sm last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

function entrySummary(entry: ExerciseHistoryEntry, ex: Exercise): string {
  const sets = entry.sets;
  if (ex.tracking_type === "cardio") {
    return sets
      .map((s) => [durationText(s.duration_seconds), s.distance ? `${num(s.distance)} mi` : null, s.speed ? `${num(s.speed)} mph` : null].filter(Boolean).join(" · "))
      .join("; ");
  }
  const side = (s: (typeof sets)[number]) => (s.side === "left" ? "L " : s.side === "right" ? "R " : "");
  if (ex.tracking_type === "timed") return sets.map((s) => `${side(s)}${durationText(s.duration_seconds)}`).join(", ");
  const weights = new Set(sets.map((s) => s.weight));
  if (weights.size === 1) {
    const w = sets[0]?.weight;
    const prefix = w ? `${isWeighted(entry.load_type) ? "" : "+"}${num(w)} lb × ` : "";
    return prefix + sets.map((s) => `${side(s)}${s.repetitions ?? "–"}`).join(", ");
  }
  return sets.map((s) => `${side(s)}${num(s.weight)}×${s.repetitions ?? "–"}`).join(", ");
}

export default function ExerciseDetailPage() {
  const { exerciseId = "" } = useParams();
  const exercise = useQuery({ queryKey: ["exercise", exerciseId], queryFn: () => api.exercise(exerciseId) });
  const progress = useQuery({ queryKey: ["exercise-progress", exerciseId], queryFn: () => api.exerciseProgress(exerciseId) });
  const [editOpen, setEditOpen] = React.useState(false);
  const fileRef = React.useRef<HTMLInputElement>(null);

  const onSaved = (ex: Exercise) => {
    queryClient.setQueryData(["exercise", ex.id], ex);
    void queryClient.invalidateQueries({ queryKey: ["exercises"] });
    void queryClient.invalidateQueries({ queryKey: ["templates"] });
  };
  const update = useMutation({ mutationFn: (body: Parameters<typeof api.updateExercise>[1]) => api.updateExercise(exerciseId, body), onSuccess: onSaved });
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadExerciseImage(exerciseId, file),
    onSuccess: (ex) => {
      onSaved(ex);
      toast.success("Image updated");
    },
  });

  if (exercise.isError) return <p className="py-16 text-center text-muted-foreground">Exercise not found.</p>;
  if (!exercise.data) {
    return (
      <div className="space-y-3 pt-10">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-64" />
      </div>
    );
  }
  const ex = exercise.data;
  const p = progress.data;
  const weighted = isWeighted(ex.load_type);
  const points = p?.points ?? [];
  const weightSeries = points.map((pt) => ({ label: dateShort(pt.performed_on), value: pt.top_weight, detail: pt.best_reps !== null ? `best set ${pt.best_reps} reps` : undefined }));
  const repSeries = points.map((pt) => ({ label: dateShort(pt.performed_on), value: pt.total_reps }));
  const durationSeries = points.map((pt) => ({ label: dateShort(pt.performed_on), value: pt.total_duration ? Math.round(pt.total_duration / (ex.tracking_type === "cardio" ? 60 : 1)) : null }));
  const distanceSeries = points.map((pt) => ({ label: dateShort(pt.performed_on), value: pt.total_distance }));

  return (
    <div>
      <header className="pb-5 pt-4 lg:pt-10">
        <Button asChild variant="ghost" size="sm" className="-ml-3 text-muted-foreground">
          <Link to="/exercises">
            <ChevronLeft /> Exercises
          </Link>
        </Button>
        <div className="mt-1 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-[28px] font-bold leading-tight tracking-tight">{ex.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {[ex.primary_muscle_group, ...ex.secondary_muscles].filter(Boolean).join(" · ")}
              <span className="text-subtle"> · {ex.id}</span>
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {!ex.enabled && <Badge variant="destructive">Disabled</Badge>}
              {ex.scheduled_in.map((t) => (
                <Badge key={t} variant="primary">
                  {t}
                </Badge>
              ))}
            </div>
          </div>
          <Button variant="secondary" size="sm" onClick={() => setEditOpen(true)}>
            <Pencil /> Edit
          </Button>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[18rem_1fr]">
        <div className="space-y-3">
          <ExerciseImage thumbUrl={ex.thumb_url} imageUrl={ex.image_url} alt={ex.name} zoomable className="aspect-[4/5] w-full max-w-xs" />
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
              e.target.value = "";
            }}
          />
          <Button variant="ghost" size="sm" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
            <ImagePlus /> {ex.image_url ? "Replace image" : "Add image"}
          </Button>
          <Card className="px-4 py-1">
            <Detail label="Equipment" value={ex.equipment_detail ?? ex.equipment_name ?? "–"} />
            {ex.attachment && <Detail label="Attachment" value={ex.attachment} />}
            <Detail label="Tracking" value={TRACKING_LABEL[ex.tracking_type]} />
            <Detail label="Weights recorded as" value={loadLabel(ex.load_type, ex.pulley_ratio) ?? LOAD_LABEL[ex.load_type]} />
            {ex.pulley_ratio && <Detail label="Pulley ratio" value={ex.pulley_ratio} />}
            <Detail label="Left / right tracked" value={ex.unilateral ? "Yes" : "No"} />
            {weighted && <Detail label="Starting weight" value={lb(ex.starting_weight)} />}
          </Card>
          {ex.notes && <p className="rounded-xl bg-muted/60 p-3 text-sm text-muted-foreground">{ex.notes}</p>}
          <Button
            variant={ex.enabled ? "ghost" : "secondary"}
            size="sm"
            className={ex.enabled ? "text-muted-foreground" : undefined}
            onClick={() => update.mutate({ enabled: !ex.enabled })}
          >
            <Power /> {ex.enabled ? "Mark unavailable" : "Make available again"}
          </Button>
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {weighted ? (
              <StatTile
                label="Best weight"
                value={lb(p?.best_weight)}
                hint={p?.best_weight_date ? `${p.best_weight_reps ?? "–"} reps · ${dateShort(p.best_weight_date)}` : undefined}
              />
            ) : (
              <StatTile label="Total reps" value={compactNumber(p?.total_reps ?? 0)} />
            )}
            <StatTile label="Sessions" value={p?.sessions ?? 0} />
            {weighted && <StatTile label="Total volume" value={`${compactNumber(p?.total_volume ?? 0)}`} hint="lb × reps, as recorded" />}
            {weighted && <StatTile label="Total reps" value={compactNumber(p?.total_reps ?? 0)} />}
          </div>

          {points.length > 0 ? (
            <>
              {weighted && (
                <Card>
                  <CardHeader>
                    <CardTitle>Working weight</CardTitle>
                    <p className="text-sm text-muted-foreground">Heaviest completed set each session ({loadLabel(ex.load_type, ex.pulley_ratio)})</p>
                  </CardHeader>
                  <CardContent>
                    <LineTrend data={weightSeries} unit="lb" />
                  </CardContent>
                </Card>
              )}
              {ex.tracking_type === "cardio" ? (
                <>
                  <Card>
                    <CardHeader>
                      <CardTitle>Duration</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <BarTrend data={durationSeries} unit="min" />
                    </CardContent>
                  </Card>
                  {distanceSeries.some((d) => d.value) && (
                    <Card>
                      <CardHeader>
                        <CardTitle>Distance</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <LineTrend data={distanceSeries} unit="mi" />
                      </CardContent>
                    </Card>
                  )}
                </>
              ) : ex.tracking_type === "timed" ? (
                <Card>
                  <CardHeader>
                    <CardTitle>Total hold time</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <BarTrend data={durationSeries} unit="sec" />
                  </CardContent>
                </Card>
              ) : (
                <Card>
                  <CardHeader>
                    <CardTitle>Total reps</CardTitle>
                    <p className="text-sm text-muted-foreground">All completed sets each session</p>
                  </CardHeader>
                  <CardContent>
                    <BarTrend data={repSeries} unit="reps" />
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            !progress.isLoading && (
              <Card className="p-6 text-center text-sm text-muted-foreground">No history yet. Progress charts appear after your first workout with this exercise.</Card>
            )
          )}

          {p && p.history.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>History</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <ul className="divide-y divide-border">
                  {p.history.map((h) => (
                    <li key={h.session_id}>
                      <Link to={`/history/${h.session_id}`} className="flex items-baseline justify-between gap-4 py-3 hover:opacity-80">
                        <div className="min-w-0">
                          <div className="text-sm text-muted-foreground">
                            {dateShort(h.performed_on)} · {h.session_name}
                          </div>
                          <div className="tabular font-medium">{entrySummary(h, ex)}</div>
                          {h.load_type !== ex.load_type && <div className="text-xs text-warning">Recorded as {loadLabel(h.load_type, h.pulley_ratio)}</div>}
                        </div>
                        {h.volume > 0 && <span className="tabular shrink-0 text-sm text-subtle">{compactNumber(h.volume)} vol</span>}
                      </Link>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent title="Edit exercise" description="Changes don't alter recorded workouts.">
          <ExerciseForm
            initial={ex}
            submitLabel="Save changes"
            onSubmit={async (body) => {
              await update.mutateAsync(body);
              setEditOpen(false);
            }}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
