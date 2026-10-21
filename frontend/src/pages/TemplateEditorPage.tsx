import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ChevronLeft, EyeOff, MoreVertical, Pencil, Play, Plus, Trash2, Undo2 } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ExerciseImage } from "@/components/ExerciseImage";
import { ExercisePicker } from "@/components/ExercisePicker";
import { Stepper } from "@/components/Stepper";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { ApiError, api } from "@/lib/api";
import { WEEKDAYS, isWeighted, lb, loadLabel, minutesText, restText, targetText } from "@/lib/format";
import { queryClient } from "@/lib/queryClient";
import type { Template, TemplateExercise, TemplateExerciseInput } from "@/lib/types";

const REST_OPTIONS = [0, 30, 45, 60, 75, 90, 120, 150, 180, 240];

function EditExerciseDialog({
  te,
  rampWeeks,
  onOpenChange,
  onSave,
}: {
  te: TemplateExercise | null;
  rampWeeks: number;
  onOpenChange: (o: boolean) => void;
  onSave: (body: TemplateExerciseInput) => Promise<unknown>;
}) {
  const [form, setForm] = React.useState<TemplateExerciseInput>({});
  const [saving, setSaving] = React.useState(false);
  React.useEffect(() => {
    if (te)
      setForm({
        ramp_sets: te.ramp_sets,
        target_sets: te.target_sets,
        target_rep_min: te.target_rep_min,
        target_rep_max: te.target_rep_max,
        target_duration_min: te.target_duration_min,
        target_duration_max: te.target_duration_max,
        per_side: te.per_side,
        suggested_weight: te.suggested_weight,
        default_rest_seconds: te.default_rest_seconds,
        notes: te.notes,
      });
  }, [te]);
  if (!te) return null;

  const ex = te.exercise;
  const usesDuration = ex.tracking_type === "cardio" || ex.tracking_type === "timed" || te.target_duration_min !== null;
  const minutes = ex.tracking_type === "cardio";
  const set = (patch: TemplateExerciseInput) => setForm((f) => ({ ...f, ...patch }));
  const durMin = form.target_duration_min ?? null;
  const durMax = form.target_duration_max ?? null;
  const toUnit = (s: number | null) => (s === null ? null : minutes ? Math.round(s / 60) : s);
  const fromUnit = (v: number) => (minutes ? v * 60 : v);

  return (
    <Dialog open={!!te} onOpenChange={onOpenChange}>
      <DialogContent title={ex.name} description="Changes apply to future workouts only. Past sessions are never changed.">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label={rampWeeks ? `Sets · weeks 1–${rampWeeks}` : "Ramp-in sets"}>
              <Stepper label="Ramp-in sets" value={form.ramp_sets ?? null} min={1} max={20} onChange={(v) => set({ ramp_sets: v })} />
            </Field>
            <Field label={rampWeeks ? `Sets · week ${rampWeeks + 1}+` : "Sets"}>
              <Stepper label="Sets" value={form.target_sets ?? null} min={1} max={20} onChange={(v) => set({ target_sets: v })} />
            </Field>
          </div>
          {usesDuration ? (
            <div className="grid grid-cols-2 gap-3">
              <Field label={`Min ${minutes ? "minutes" : "seconds"}`}>
                <Stepper
                  label="Minimum duration"
                  value={toUnit(durMin)}
                  step={minutes ? 1 : 5}
                  max={minutes ? 360 : 3600}
                  onChange={(v) => set({ target_duration_min: fromUnit(v), ...(durMax !== null && fromUnit(v) > durMax ? { target_duration_max: fromUnit(v) } : {}) })}
                />
              </Field>
              <Field label={`Max ${minutes ? "minutes" : "seconds"}`}>
                <Stepper
                  label="Maximum duration"
                  value={toUnit(durMax)}
                  step={minutes ? 1 : 5}
                  max={minutes ? 360 : 3600}
                  onChange={(v) => set({ target_duration_max: fromUnit(v), ...(durMin !== null && fromUnit(v) < durMin ? { target_duration_min: fromUnit(v) } : {}) })}
                />
              </Field>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <Field label="Min reps">
                <Stepper
                  label="Minimum reps"
                  value={form.target_rep_min ?? null}
                  min={1}
                  max={100}
                  onChange={(v) => set({ target_rep_min: v, ...((form.target_rep_max ?? 0) < v ? { target_rep_max: v } : {}) })}
                />
              </Field>
              <Field label="Max reps">
                <Stepper
                  label="Maximum reps"
                  value={form.target_rep_max ?? null}
                  min={1}
                  max={100}
                  onChange={(v) => set({ target_rep_max: v, ...((form.target_rep_min ?? 0) > v ? { target_rep_min: v } : {}) })}
                />
              </Field>
            </div>
          )}
          <div className="flex items-center justify-between rounded-xl border border-border px-4 py-3">
            <div>
              <div className="font-medium">Per side</div>
              <div className="text-sm text-muted-foreground">Target is for each side / leg</div>
            </div>
            <Switch checked={!!form.per_side} onCheckedChange={(v) => set({ per_side: v })} />
          </div>
          {isWeighted(ex.load_type) && (
            <Field label="Default working weight" hint={`${loadLabel(ex.load_type, ex.pulley_ratio)}. Used when you haven't done this exercise yet, or when changed here more recently than your last workout.`}>
              <Stepper label="Default weight" unit="lb" decimals step={5} value={form.suggested_weight ?? null} onChange={(v) => set({ suggested_weight: v })} />
            </Field>
          )}
          <Field label="Rest between sets">
            <Select value={form.default_rest_seconds ?? 90} onChange={(e) => set({ default_rest_seconds: Number(e.target.value) })}>
              {[...new Set([...REST_OPTIONS, form.default_rest_seconds ?? 90])]
                .sort((a, b) => a - b)
                .map((s) => (
                  <option key={s} value={s}>
                    {restText(s)}
                  </option>
                ))}
            </Select>
          </Field>
          <Field label="Notes">
            <Textarea value={form.notes ?? ""} onChange={(e) => set({ notes: e.target.value || null })} placeholder="Setup, cues, protocol…" />
          </Field>
          <Button
            className="w-full"
            disabled={saving}
            onClick={async () => {
              setSaving(true);
              try {
                const body = { ...form };
                if (body.suggested_weight === te.suggested_weight) delete body.suggested_weight;
                await onSave(body);
                onOpenChange(false);
              } finally {
                setSaving(false);
              }
            }}
          >
            Save
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RenameDialog({ template, open, onOpenChange }: { template: Template; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [name, setName] = React.useState(template.name);
  const [notes, setNotes] = React.useState(template.notes ?? "");
  const [minutes, setMinutes] = React.useState<string>(template.estimated_duration_override?.toString() ?? "");
  React.useEffect(() => {
    if (open) {
      setName(template.name);
      setNotes(template.notes ?? "");
      setMinutes(template.estimated_duration_override?.toString() ?? "");
    }
  }, [open, template]);
  const save = useMutation({
    mutationFn: () =>
      api.updateTemplate(template.id, {
        name: name.trim(),
        notes: notes.trim() || null,
        estimated_duration_minutes: minutes ? Number(minutes) : null,
      }),
    onSuccess: (t) => {
      queryClient.setQueryData(["template", t.id], t);
      void queryClient.invalidateQueries({ queryKey: ["templates"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onOpenChange(false);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Workout details">
        <div className="space-y-3">
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Estimated duration (minutes)" hint="Leave empty to estimate from sets and rest times.">
            <Input type="number" inputMode="numeric" value={minutes} onChange={(e) => setMinutes(e.target.value)} placeholder={String(template.estimated_duration_minutes)} />
          </Field>
          <Field label="Notes">
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
          <Button className="w-full" disabled={!name.trim() || save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function TemplateEditorPage() {
  const { templateId } = useParams();
  const id = Number(templateId);
  const navigate = useNavigate();
  const template = useQuery({ queryKey: ["template", id], queryFn: () => api.template(id) });
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const all = useQuery({ queryKey: ["templates"], queryFn: api.templates });
  const [editing, setEditing] = React.useState<TemplateExercise | null>(null);
  const [removing, setRemoving] = React.useState<TemplateExercise | null>(null);
  const [pickerOpen, setPickerOpen] = React.useState(false);
  const [renameOpen, setRenameOpen] = React.useState(false);
  const [deleteOpen, setDeleteOpen] = React.useState(false);

  const mutate = useMutation({
    mutationFn: (fn: () => Promise<Template>) => fn(),
    onSuccess: (t) => {
      queryClient.setQueryData(["template", t.id], t);
      void queryClient.invalidateQueries({ queryKey: ["templates"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const start = useMutation({
    mutationFn: () => api.startSession(id),
    onSuccess: (s) => {
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/workout/${s.id}`);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        const active = (e.detail as { active_session_id?: number })?.active_session_id;
        if (active) navigate(`/workout/${active}`);
      }
    },
  });

  if (template.isError) return <p className="py-16 text-center text-muted-foreground">Workout not found.</p>;
  if (!template.data) {
    return (
      <div className="space-y-3 pt-10">
        <Skeleton className="h-12 w-1/2" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
    );
  }

  const t = template.data;
  const rampWeeks = settings.data?.ramp_weeks ?? 2;
  const move = (index: number, dir: -1 | 1) => {
    const ids = t.exercises.map((e) => e.id);
    const j = index + dir;
    if (j < 0 || j >= ids.length) return;
    [ids[index], ids[j]] = [ids[j], ids[index]];
    mutate.mutate(() => api.reorderTemplate(t.id, ids));
  };
  const occupantOf = (day: number) => all.data?.find((x) => x.weekday === day && x.id !== t.id);

  return (
    <div>
      <header className="pb-4 pt-4 lg:pt-10">
        <Button asChild variant="ghost" size="sm" className="-ml-3 text-muted-foreground">
          <Link to="/schedule">
            <ChevronLeft /> Weekly plan
          </Link>
        </Button>
        <div className="mt-1 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-[28px] font-bold leading-tight tracking-tight">{t.name}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {t.exercise_count} exercises · ~{minutesText(t.estimated_duration_minutes)}
            </p>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Workout options">
                <MoreVertical />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onSelect={() => setRenameOpen(true)}>
                <Pencil /> Rename & details
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem destructive onSelect={() => setDeleteOpen(true)}>
                <Trash2 /> Delete workout
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        {t.notes && <p className="mt-2 text-sm text-muted-foreground">{t.notes}</p>}
        <div className="grid grid-cols-1 mt-4 gap-3 sm:grid-cols-[1fr_auto]">
          <Select
            aria-label="Scheduled day"
            value={t.weekday ?? ""}
            onChange={(e) => {
              const v = e.target.value;
              const occupant = v === "" ? undefined : occupantOf(Number(v));
              mutate.mutate(() => api.updateTemplate(t.id, v === "" ? { unschedule: true } : { weekday: Number(v) }));
              if (occupant) toast.info(`${occupant.name} moved to ${t.weekday !== null ? WEEKDAYS[t.weekday] : "unscheduled"}`);
            }}
          >
            <option value="">Not scheduled</option>
            {WEEKDAYS.map((d, i) => (
              <option key={d} value={i}>
                Every {d}
                {occupantOf(i) ? ` (swap with ${occupantOf(i)!.name})` : ""}
              </option>
            ))}
          </Select>
          <Button onClick={() => start.mutate()} disabled={start.isPending || !t.exercise_count}>
            <Play /> Start this workout
          </Button>
        </div>
      </header>

      <div className="space-y-2.5">
        {t.exercises.map((te, i) => (
          <Card key={te.id} className={te.skipped ? "opacity-60" : undefined}>
            <div className="flex items-center gap-3 p-3 sm:p-4">
              <div className="flex flex-col">
                <button
                  className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-25"
                  disabled={i === 0 || mutate.isPending}
                  onClick={() => move(i, -1)}
                  aria-label={`Move ${te.exercise.name} up`}
                >
                  <ArrowUp className="size-4" />
                </button>
                <button
                  className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted disabled:opacity-25"
                  disabled={i === t.exercises.length - 1 || mutate.isPending}
                  onClick={() => move(i, 1)}
                  aria-label={`Move ${te.exercise.name} down`}
                >
                  <ArrowDown className="size-4" />
                </button>
              </div>
              <ExerciseImage thumbUrl={te.exercise.thumb_url} imageUrl={te.exercise.image_url} alt={te.exercise.name} zoomable className="size-14 shrink-0" />
              <button className="min-w-0 flex-1 text-left" onClick={() => setEditing(te)}>
                <div className="line-clamp-2 font-semibold leading-snug">{te.exercise.name}</div>
                <div className="text-sm text-muted-foreground">
                  {te.ramp_sets && te.ramp_sets !== te.target_sets ? `${te.ramp_sets}→${te.target_sets}` : te.target_sets} sets ·{" "}
                  {targetText(te, te.exercise.tracking_type)}
                  {isWeighted(te.exercise.load_type) && te.suggested_weight !== null ? ` · ${lb(te.suggested_weight)}` : ""}
                  {te.default_rest_seconds ? ` · rest ${restText(te.default_rest_seconds)}` : ""}
                </div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {te.skipped && <Badge variant="warning">Skipped for now</Badge>}
                  {!te.exercise.enabled && <Badge variant="destructive">Exercise disabled</Badge>}
                  {te.notes && <Badge variant="outline" className="max-w-full truncate">{te.notes}</Badge>}
                </div>
              </button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon-sm" aria-label={`Options for ${te.exercise.name}`}>
                    <MoreVertical />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  <DropdownMenuItem onSelect={() => setEditing(te)}>
                    <Pencil /> Edit sets, reps & weight
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => mutate.mutate(() => api.updateTemplateExercise(t.id, te.id, { skipped: !te.skipped }))}>
                    {te.skipped ? <Undo2 /> : <EyeOff />}
                    {te.skipped ? "Include again" : "Skip temporarily"}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem destructive onSelect={() => setRemoving(te)}>
                    <Trash2 /> Remove from workout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </Card>
        ))}
        <Button variant="secondary" size="lg" className="w-full" onClick={() => setPickerOpen(true)}>
          <Plus /> Add exercise
        </Button>
      </div>

      <EditExerciseDialog
        te={editing}
        rampWeeks={rampWeeks}
        onOpenChange={(o) => !o && setEditing(null)}
        onSave={(body) => mutate.mutateAsync(() => api.updateTemplateExercise(t.id, editing!.id, body))}
      />
      <ExercisePicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        title={`Add to ${t.name}`}
        existing={t.exercises.map((e) => e.exercise.id)}
        onPick={async (ex) => {
          await mutate.mutateAsync(() => api.addTemplateExercise(t.id, { exercise_id: ex.id }));
          toast.success(`${ex.name} added`);
        }}
      />
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={`Remove ${removing?.exercise.name}?`}
        description="It will no longer be part of this workout. Your recorded history for it is kept."
        confirmLabel="Remove"
        destructive
        onConfirm={async () => {
          await mutate.mutateAsync(() => api.removeTemplateExercise(t.id, removing!.id));
        }}
      />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={`Delete ${t.name}?`}
        description="The workout plan is removed. Workouts you already recorded with it stay in your history."
        confirmLabel="Delete workout"
        destructive
        onConfirm={async () => {
          await api.deleteTemplate(t.id);
          await queryClient.invalidateQueries();
          navigate("/schedule", { replace: true });
        }}
      />
      <RenameDialog template={t} open={renameOpen} onOpenChange={setRenameOpen} />
    </div>
  );
}
