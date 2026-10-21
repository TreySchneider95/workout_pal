import { Check, ChevronLeft, Clock, MoreHorizontal, Pencil, Play, Plus, Trash2, X } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ExerciseImage } from "@/components/ExerciseImage";
import { ExercisePicker } from "@/components/ExercisePicker";
import { ExerciseTracker } from "@/components/ExerciseTracker";
import { SaveIndicator } from "@/components/SaveIndicator";
import { setLabel } from "@/components/SetRow";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown";
import { Field, Input, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { useSessionEditor } from "@/hooks/useSessionEditor";
import { ApiError, api } from "@/lib/api";
import { saveQueue } from "@/lib/autosave";
import { dateLong, durationText, isWeighted, loadLabel, minutesText, num, targetText, timeOfDay } from "@/lib/format";
import { queryClient } from "@/lib/queryClient";
import type { SessionExercise, WorkoutSession } from "@/lib/types";
import { cn } from "@/lib/utils";

function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function SetsTable({ exercise }: { exercise: SessionExercise }) {
  const t = exercise.tracking_type;
  const weighted = isWeighted(exercise.load_type);
  const columns =
    t === "cardio"
      ? ["Duration", "Distance", "Speed"]
      : t === "timed"
        ? [weighted ? "Weight" : null, "Hold"].filter(Boolean)
        : [weighted ? "Weight" : "Added", "Reps"];
  return (
    <table className="tabular w-full text-sm">
      <thead>
        <tr className="text-left text-[11px] uppercase tracking-wider text-subtle">
          <th className="w-12 py-1.5 font-semibold">Set</th>
          {columns.map((c) => (
            <th key={c} className="py-1.5 font-semibold">
              {c}
            </th>
          ))}
          <th className="w-8 py-1.5" />
        </tr>
      </thead>
      <tbody>
        {exercise.sets.map((s) => (
          <tr key={s.id} className={cn("border-t border-border", !s.completed && "text-subtle")}>
            <td className="py-2 font-semibold">{setLabel(s)}</td>
            {t === "cardio" ? (
              <>
                <td>{durationText(s.duration_seconds)}</td>
                <td>{s.distance !== null ? `${num(s.distance)} mi` : "–"}</td>
                <td>{s.speed !== null ? `${num(s.speed)} mph` : "–"}</td>
              </>
            ) : t === "timed" ? (
              <>
                {weighted && <td>{num(s.weight)} lb</td>}
                <td>{durationText(s.duration_seconds)}</td>
              </>
            ) : (
              <>
                <td>{weighted ? `${num(s.weight)} lb` : s.weight ? `+${num(s.weight)} lb` : "BW"}</td>
                <td>{num(s.repetitions)}</td>
              </>
            )}
            <td className="text-right">
              {s.completed ? <Check className="ml-auto size-4 text-primary" aria-label="Completed" /> : <X className="ml-auto size-4" aria-label="Not completed" />}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ExerciseResult({ exercise }: { exercise: SessionExercise }) {
  const load = loadLabel(exercise.load_type, exercise.pulley_ratio);
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex items-start gap-3">
        <ExerciseImage thumbUrl={exercise.thumb_url} imageUrl={exercise.image_url} alt={exercise.exercise_name} zoomable className="size-14 shrink-0" />
        <div className="min-w-0 flex-1">
          <Link to={`/exercises/${exercise.exercise_id}`} className="font-semibold hover:underline">
            {exercise.exercise_name}
          </Link>
          <div className="mt-1 flex flex-wrap gap-1.5">
            <Badge>
              Target {exercise.target_sets} × {targetText(exercise, exercise.tracking_type)}
            </Badge>
            {load && <Badge variant="outline">{load}</Badge>}
            {exercise.status === "skipped" && <Badge variant="warning">Skipped</Badge>}
          </div>
        </div>
      </div>
      {exercise.sets.some((s) => s.completed) ? (
        <div className="mt-3">
          <SetsTable exercise={exercise} />
        </div>
      ) : (
        exercise.status !== "skipped" && <p className="mt-3 text-sm text-subtle">Not performed</p>
      )}
      {exercise.notes && <p className="mt-3 rounded-xl bg-muted/60 p-3 text-sm text-muted-foreground">{exercise.notes}</p>}
    </Card>
  );
}

function DetailsDialog({ session, open, onOpenChange }: { session: WorkoutSession; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [name, setName] = React.useState(session.name);
  const [day, setDay] = React.useState(session.performed_on);
  const [start, setStart] = React.useState(toLocalInput(session.started_at));
  const [end, setEnd] = React.useState(toLocalInput(session.completed_at));
  const [notes, setNotes] = React.useState(session.notes ?? "");
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (open) {
      setName(session.name);
      setDay(session.performed_on);
      setStart(toLocalInput(session.started_at));
      setEnd(toLocalInput(session.completed_at));
      setNotes(session.notes ?? "");
    }
  }, [open, session]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Edit workout details">
        <div className="space-y-3">
          <Field label="Name">
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Date">
            <Input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Started">
              <Input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} />
            </Field>
            <Field label="Finished">
              <Input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} />
            </Field>
          </div>
          <Field label="Notes">
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
          </Field>
          <Button
            className="w-full"
            disabled={saving || !name.trim()}
            onClick={async () => {
              setSaving(true);
              try {
                await api.updateSession(session.id, {
                  name: name.trim(),
                  performed_on: day,
                  started_at: start ? new Date(start).toISOString() : undefined,
                  completed_at: end ? new Date(end).toISOString() : session.completed_at,
                  notes: notes.trim() || null,
                });
                await queryClient.invalidateQueries();
                onOpenChange(false);
              } catch (e) {
                toast.error(e instanceof Error ? e.message : "Could not save");
              } finally {
                setSaving(false);
              }
            }}
          >
            Save details
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function SessionDetailPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();
  const editor = useSessionEditor(id);
  const session = editor.session;
  const [editing, setEditing] = React.useState(false);
  const [detailsOpen, setDetailsOpen] = React.useState(false);
  const [deleteOpen, setDeleteOpen] = React.useState(false);
  const [pickerOpen, setPickerOpen] = React.useState(false);

  if (editor.query.isError && !session) {
    return <p className="py-16 text-center text-muted-foreground">Workout not found.</p>;
  }
  if (!session) {
    return (
      <div className="space-y-3 pt-10">
        <Skeleton className="h-12 w-2/3" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  const duration =
    session.completed_at !== null
      ? Math.round((new Date(session.completed_at).getTime() - new Date(session.started_at).getTime()) / 60000)
      : null;

  return (
    <div>
      <header className="pb-5 pt-4 lg:pt-10">
        <Button asChild variant="ghost" size="sm" className="-ml-3 text-muted-foreground">
          <Link to="/history">
            <ChevronLeft /> History
          </Link>
        </Button>
        <div className="mt-1 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-muted-foreground">{dateLong(session.performed_on)}</p>
            <h1 className="text-[28px] font-bold leading-tight tracking-tight">{session.name}</h1>
            <p className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <Clock className="size-4" />
                {timeOfDay(session.started_at)}
                {session.completed_at && ` – ${timeOfDay(session.completed_at)}`}
                {duration !== null && ` · ${minutesText(duration)}`}
              </span>
              <span>
                {session.completed_sets}/{session.total_sets} sets
              </span>
            </p>
          </div>
          <div className="flex shrink-0 gap-1">
            <Button variant={editing ? "default" : "secondary"} size="sm" onClick={() => setEditing((v) => !v)}>
              {editing ? <Check /> : <Pencil />}
              {editing ? "Done" : "Edit"}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label="More">
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem onSelect={() => setDetailsOpen(true)}>
                  <Pencil /> Edit name, date & times
                </DropdownMenuItem>
                {session.status === "completed" && (
                  <DropdownMenuItem
                    onSelect={async () => {
                      try {
                        await api.resumeSession(id);
                        await queryClient.invalidateQueries();
                        navigate(`/workout/${id}`);
                      } catch (e) {
                        toast.error(e instanceof ApiError ? e.message : "Could not reopen");
                      }
                    }}
                  >
                    <Play /> Reopen as in progress
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem destructive onSelect={() => setDeleteOpen(true)}>
                  <Trash2 /> Delete workout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        {session.status === "in_progress" && (
          <Button asChild className="mt-3 w-full" size="lg">
            <Link to={`/workout/${id}`}>
              <Play /> Resume workout
            </Link>
          </Button>
        )}
        {session.notes && !editing && <p className="mt-3 rounded-xl bg-muted/60 p-3 text-sm italic text-muted-foreground">“{session.notes}”</p>}
      </header>

      {editing && (
        <div className="mb-4 flex items-center justify-between rounded-xl border border-info/30 bg-info-soft px-4 py-3 text-sm">
          <span>Editing recorded sets. Changes save automatically.</span>
          <SaveIndicator />
        </div>
      )}

      <div className="space-y-3">
        {session.exercises.map((e) =>
          editing ? (
            <ExerciseTracker
              key={e.id}
              exercise={e}
              busy={editor.busy}
              onSetChange={editor.changeSet}
              onAddSet={() => editor.addSet(e)}
              onRemoveLastSet={() => editor.removeLastSet(e)}
              onToggleSkip={() => editor.toggleSkip(e)}
              onNotesSave={(n) => editor.saveNotes(e, n)}
            />
          ) : (
            <ExerciseResult key={e.id} exercise={e} />
          ),
        )}
        {editing && (
          <Button variant="secondary" className="w-full" onClick={() => setPickerOpen(true)}>
            <Plus /> Add an exercise
          </Button>
        )}
      </div>

      <DetailsDialog session={session} open={detailsOpen} onOpenChange={setDetailsOpen} />
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete this workout?"
        description="This permanently removes the workout and every recorded set from your history."
        confirmLabel="Delete workout"
        destructive
        onConfirm={async () => {
          await api.deleteSession(id);
          saveQueue.dropSession(id);
          await queryClient.invalidateQueries();
          navigate("/history", { replace: true });
        }}
      />
      <ExercisePicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        existing={session.exercises.map((e) => e.exercise_id)}
        onPick={async (ex) => {
          await editor.addExercise(ex.id);
          setPickerOpen(false);
        }}
      />
    </div>
  );
}
