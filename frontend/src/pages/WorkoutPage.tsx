import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Flag, ListOrdered, MoreHorizontal, Plus, RotateCcw, Timer, Trash2 } from "lucide-react";
import * as React from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ExerciseImage } from "@/components/ExerciseImage";
import { ExercisePicker } from "@/components/ExercisePicker";
import { ExerciseTracker } from "@/components/ExerciseTracker";
import { SaveIndicator } from "@/components/SaveIndicator";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown";
import { Field, Textarea } from "@/components/ui/input";
import { Progress, Skeleton } from "@/components/ui/misc";
import { useRestTimer } from "@/hooks/restTimer";
import { forgetCachedSession, useSessionEditor } from "@/hooks/useSessionEditor";
import { api } from "@/lib/api";
import { saveQueue } from "@/lib/autosave";
import { clock } from "@/lib/format";
import { queryClient } from "@/lib/queryClient";
import type { SessionExercise, SetPatch } from "@/lib/types";
import { cn } from "@/lib/utils";
import { nextExerciseIndex } from "@/lib/workoutFlow";

function Elapsed({ since }: { since: string }) {
  const [now, setNow] = React.useState(Date.now());
  React.useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return <span className="tabular">{clock((now - new Date(since).getTime()) / 1000)}</span>;
}

function exerciseState(e: SessionExercise): "done" | "partial" | "skipped" | "todo" {
  if (e.status === "skipped") return "skipped";
  const done = e.sets.filter((s) => s.completed).length;
  if (done && done === e.sets.length) return "done";
  return done ? "partial" : "todo";
}

const indexKey = (id: number) => `workoutpal:session:${id}:index`;

export default function WorkoutPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();
  const editor = useSessionEditor(id);
  const { session } = editor;
  const timer = useRestTimer();
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });

  const [index, setIndex] = React.useState(() => {
    try {
      return Number(localStorage.getItem(indexKey(id)) ?? 0) || 0;
    } catch {
      return 0;
    }
  });
  const [finishOpen, setFinishOpen] = React.useState(false);
  const [discardOpen, setDiscardOpen] = React.useState(false);
  const [pickerOpen, setPickerOpen] = React.useState(false);
  const [overviewOpen, setOverviewOpen] = React.useState(false);
  const [notes, setNotes] = React.useState("");
  const [finishing, setFinishing] = React.useState(false);
  const topRef = React.useRef<HTMLDivElement>(null);

  const exercises = session?.exercises ?? [];
  const current = exercises[Math.min(index, Math.max(0, exercises.length - 1))];

  const goTo = (i: number) => {
    const next = Math.max(0, Math.min(exercises.length - 1, i));
    setIndex(next);
    try {
      localStorage.setItem(indexKey(id), String(next));
    } catch {
      /* ignore */
    }
    topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  React.useEffect(() => {
    if (session?.notes) setNotes(session.notes);
  }, [session?.notes]);

  if (editor.query.isError && !session) {
    return (
      <div className="py-16 text-center">
        <p className="text-muted-foreground">Could not load this workout.</p>
        <Button className="mt-4" onClick={() => editor.refresh()}>
          Try again
        </Button>
      </div>
    );
  }
  if (!session) {
    return (
      <div className="space-y-4 pt-6">
        <Skeleton className="h-14" />
        <Skeleton className="h-10" />
        <Skeleton className="h-[28rem]" />
      </div>
    );
  }
  if (session.status === "completed") return <Navigate to={`/history/${session.id}`} replace />;

  const allSets = exercises.filter((e) => e.status !== "skipped").flatMap((e) => e.sets);
  const doneSets = allSets.filter((s) => s.completed).length;
  const progress = allSets.length ? (doneSets / allSets.length) * 100 : 0;
  const currentIndex = current ? exercises.indexOf(current) : 0;
  // Next skips finished exercises and wraps to the top, so you can do one set of
  // each exercise per round. Nothing left elsewhere → offer Finish instead.
  const nextIndex = nextExerciseIndex(exercises, currentIndex);
  const nextIsNewRound = nextIndex !== null && nextIndex < currentIndex;

  const onSetChange = (se: SessionExercise, setId: number, patch: SetPatch) => {
    editor.changeSet(setId, patch);
    if (patch.completed && settings.data?.rest_timer_auto_start !== false && se.rest_seconds > 0) {
      const target = se.sets.find((s) => s.id === setId);
      const siblingsDone = se.sets.filter((s) => target && s.set_number === target.set_number && s.id !== setId).every((s) => s.completed);
      if (siblingsDone) timer.start(se.rest_seconds, `Rest · ${se.exercise_name}`);
    }
  };

  const finish = async () => {
    setFinishing(true);
    try {
      await saveQueue.flush();
      if (saveQueue.hasPending(id)) {
        toast.error("Can't reach the server. Your sets are saved on this device; try again when connected.");
        return;
      }
      await api.completeSession(id, notes.trim() || null);
      timer.stop();
      localStorage.removeItem(indexKey(id));
      await queryClient.invalidateQueries();
      toast.success("Workout saved");
      navigate(`/history/${id}`, { replace: true });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not finish workout");
    } finally {
      setFinishing(false);
    }
  };

  const remaining = allSets.length - doneSets;

  return (
    <div ref={topRef} className="scroll-mt-0">
      {/* Sticky workout header */}
      <div className="sticky top-0 z-20 -mx-4 border-b border-border bg-background/90 px-4 pb-3 pt-[calc(0.75rem+env(safe-area-inset-top))] backdrop-blur-lg lg:-mx-10 lg:px-10">
        <div className="flex items-center gap-2">
          <Button asChild variant="ghost" size="icon" className="-ml-2.5">
            <Link to="/" aria-label="Back to today">
              <ChevronLeft />
            </Link>
          </Button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-lg font-bold leading-tight">{session.name}</h1>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <Timer className="size-3.5" />
                <Elapsed since={session.started_at} />
              </span>
              <SaveIndicator />
            </div>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Workout options">
                <MoreHorizontal />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem onSelect={() => setOverviewOpen(true)}>
                <ListOrdered /> All exercises
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setPickerOpen(true)}>
                <Plus /> Add an exercise
              </DropdownMenuItem>
              {current && current.rest_seconds > 0 && (
                <DropdownMenuItem onSelect={() => timer.start(current.rest_seconds, `Rest · ${current.exercise_name}`)}>
                  <Timer /> Start rest timer
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem destructive onSelect={() => setDiscardOpen(true)}>
                <Trash2 /> Discard workout
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button size="sm" onClick={() => setFinishOpen(true)}>
            <Flag /> Finish
          </Button>
        </div>
        <div className="mt-3 flex items-center gap-3">
          <Progress value={progress} />
          <span className="tabular shrink-0 text-xs font-semibold text-muted-foreground">
            {doneSets}/{allSets.length} sets
          </span>
        </div>
        {/* Exercise navigation */}
        <div className="no-scrollbar -mx-4 mt-3 flex gap-2 overflow-x-auto px-4 lg:mx-0 lg:px-0" role="tablist" aria-label="Exercises">
          {exercises.map((e, i) => {
            const state = exerciseState(e);
            const active = e === current;
            return (
              <button
                key={e.id}
                role="tab"
                aria-selected={active}
                aria-label={`${i + 1}. ${e.exercise_name} (${state})`}
                onClick={() => goTo(i)}
                className={cn(
                  "tabular flex size-10 shrink-0 items-center justify-center rounded-full border-2 text-sm font-bold transition-all",
                  state === "done" && "border-primary bg-primary text-primary-foreground",
                  state === "partial" && "border-primary text-primary",
                  state === "skipped" && "border-dashed border-input text-subtle line-through",
                  state === "todo" && "border-input text-muted-foreground",
                  active && "ring-2 ring-foreground ring-offset-2 ring-offset-background",
                )}
              >
                {i + 1}
              </button>
            );
          })}
        </div>
      </div>

      <div className="pt-4">
        {current ? (
          <ExerciseTracker
            key={current.id}
            exercise={current}
            busy={editor.busy}
            onSetChange={(setId, patch) => onSetChange(current, setId, patch)}
            onAddSet={() => editor.addSet(current)}
            onRemoveLastSet={() => editor.removeLastSet(current)}
            onApplyWeight={(w) => editor.applyWeight(current, w)}
            onToggleSkip={() => editor.toggleSkip(current)}
            onNotesSave={(n) => editor.saveNotes(current, n)}
            onStartRest={() => timer.start(current.rest_seconds, `Rest · ${current.exercise_name}`)}
          />
        ) : (
          <div className="rounded-3xl border border-dashed border-border p-10 text-center text-muted-foreground">
            No exercises yet.
            <Button className="mt-4 w-full" onClick={() => setPickerOpen(true)}>
              <Plus /> Add an exercise
            </Button>
          </div>
        )}

        <div className="mt-4 grid grid-cols-2 gap-3">
          <Button variant="secondary" size="lg" disabled={currentIndex === 0} onClick={() => goTo(currentIndex - 1)}>
            <ChevronLeft /> Previous
          </Button>
          {nextIndex === null ? (
            <Button size="lg" onClick={() => setFinishOpen(true)}>
              <Flag /> Finish
            </Button>
          ) : nextIsNewRound ? (
            <Button
              size="lg"
              variant={current && exerciseState(current) !== "todo" ? "default" : "secondary"}
              onClick={() => goTo(nextIndex)}
              aria-label={`Next round: back to exercise ${nextIndex + 1}, ${exercises[nextIndex].exercise_name}`}
            >
              <RotateCcw /> Back to #{nextIndex + 1}
            </Button>
          ) : (
            <Button
              size="lg"
              variant={current && exerciseState(current) !== "todo" ? "default" : "secondary"}
              onClick={() => goTo(nextIndex)}
            >
              Next <ChevronRight />
            </Button>
          )}
        </div>
      </div>

      {/* Overview of all exercises */}
      <Dialog open={overviewOpen} onOpenChange={setOverviewOpen}>
        <DialogContent title="Exercises" description={`${doneSets} of ${allSets.length} sets done`}>
          <ul className="space-y-1">
            {exercises.map((e, i) => {
              const done = e.sets.filter((s) => s.completed).length;
              return (
                <li key={e.id}>
                  <button
                    className={cn("flex w-full items-center gap-3 rounded-xl p-2 text-left hover:bg-muted", e === current && "bg-muted")}
                    onClick={() => {
                      goTo(i);
                      setOverviewOpen(false);
                    }}
                  >
                    <ExerciseImage thumbUrl={e.thumb_url} imageUrl={e.image_url} alt={e.exercise_name} className="size-11 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className={cn("truncate font-medium", e.status === "skipped" && "line-through text-muted-foreground")}>
                        {i + 1}. {e.exercise_name}
                      </div>
                      <div className="text-sm text-muted-foreground">
                        {e.status === "skipped" ? "Skipped" : `${done}/${e.sets.length} sets`}
                      </div>
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </DialogContent>
      </Dialog>

      {/* Finish */}
      <Dialog open={finishOpen} onOpenChange={setFinishOpen}>
        <DialogContent title="Finish workout?" description={`${doneSets} of ${allSets.length} sets completed`}>
          {remaining > 0 && (
            <p className="mb-3 rounded-xl bg-warning-soft p-3 text-sm text-warning">
              {remaining} set{remaining === 1 ? " is" : "s are"} not marked done. They'll be kept as not completed and won't count toward your progress.
            </p>
          )}
          <Field label="Workout notes (optional)">
            <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Energy, sleep, anything worth remembering" />
          </Field>
          <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="secondary" onClick={() => setFinishOpen(false)}>
              Keep going
            </Button>
            <Button onClick={finish} disabled={finishing}>
              <Flag /> {finishing ? "Saving…" : "Finish & save"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={discardOpen}
        onOpenChange={setDiscardOpen}
        title="Discard this workout?"
        description="All sets recorded in this session will be permanently deleted. This can't be undone."
        confirmLabel="Discard workout"
        destructive
        onConfirm={async () => {
          await api.deleteSession(id);
          saveQueue.dropSession(id);
          forgetCachedSession(id);
          timer.stop();
          await queryClient.invalidateQueries();
          navigate("/", { replace: true });
        }}
      />

      <ExercisePicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        existing={exercises.map((e) => e.exercise_id)}
        onPick={async (ex) => {
          await editor.addExercise(ex.id);
          setPickerOpen(false);
          setIndex(exercises.length);
        }}
      />
    </div>
  );
}
