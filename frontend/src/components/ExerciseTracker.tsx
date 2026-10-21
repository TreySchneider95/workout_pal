import { ArrowDownRight, ArrowUpRight, History, Info, Minus, NotebookPen, Plus, SkipForward, Timer, Undo2 } from "lucide-react";
import * as React from "react";
import { Link } from "react-router";

import { ExerciseImage } from "@/components/ExerciseImage";
import { SetRow, setLabel } from "@/components/SetRow";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { dateShort, lb, loadLabel, restText, targetText } from "@/lib/format";
import type { SessionExercise, SetPatch } from "@/lib/types";
import { cn } from "@/lib/utils";

interface Props {
  exercise: SessionExercise;
  onSetChange: (setId: number, patch: SetPatch) => void;
  onAddSet: () => void;
  onRemoveLastSet: () => void;
  onApplyWeight?: (weight: number) => void;
  onToggleSkip?: () => void;
  onNotesSave: (notes: string) => void;
  onStartRest?: () => void;
  busy?: boolean;
}

function Suggestion({ exercise, onApply }: { exercise: SessionExercise; onApply?: (w: number) => void }) {
  const { suggestion_action: action, suggestion_reason: reason, recommended_weight: weight } = exercise;
  if (!action || !reason || action === "none") return null;
  const actionable = (action === "increase" || action === "decrease") && weight !== null;
  const pending = exercise.sets.filter((s) => !s.completed);
  const applied = actionable && pending.length > 0 && pending.every((s) => s.weight === weight);
  const Icon = action === "increase" ? ArrowUpRight : action === "decrease" ? ArrowDownRight : Info;
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-xl p-3 text-sm",
        action === "increase" ? "bg-primary-soft" : action === "decrease" ? "bg-warning-soft" : "bg-info-soft",
      )}
    >
      <Icon
        className={cn(
          "mt-0.5 size-[18px] shrink-0",
          action === "increase" ? "text-primary" : action === "decrease" ? "text-warning" : "text-info",
        )}
      />
      <div className="min-w-0 flex-1 text-foreground/90">{reason}</div>
      {actionable && onApply && pending.length > 0 && (
        <Button
          size="sm"
          variant={applied ? "ghost" : action === "increase" ? "default" : "secondary"}
          disabled={applied}
          onClick={() => onApply(weight)}
        >
          {applied ? "Applied" : `Use ${lb(weight)}`}
        </Button>
      )}
    </div>
  );
}

export function ExerciseTracker({
  exercise,
  onSetChange,
  onAddSet,
  onRemoveLastSet,
  onApplyWeight,
  onToggleSkip,
  onNotesSave,
  onStartRest,
  busy,
}: Props) {
  const [showNotes, setShowNotes] = React.useState(!!exercise.notes);
  const [notes, setNotes] = React.useState(exercise.notes ?? "");
  React.useEffect(() => {
    setNotes(exercise.notes ?? "");
    setShowNotes(!!exercise.notes);
  }, [exercise.id, exercise.notes]);

  const skipped = exercise.status === "skipped";
  const load = loadLabel(exercise.load_type, exercise.pulley_ratio);
  const sets = exercise.sets;
  const header =
    exercise.tracking_type === "cardio"
      ? null
      : exercise.tracking_type === "timed"
        ? ["Set", "Hold", ""]
        : ["Set", exercise.load_type === "bodyweight" ? "Added" : "Weight", "Reps"];

  return (
    <article className={cn("rounded-3xl border border-border bg-card", skipped && "opacity-60")}>
      <div className="flex gap-4 p-4 sm:p-5">
        <ExerciseImage
          thumbUrl={exercise.thumb_url}
          imageUrl={exercise.image_url}
          alt={exercise.exercise_name}
          zoomable
          className="h-[7.5rem] w-24 shrink-0 sm:h-48 sm:w-40"
        />
        <div className="min-w-0 flex-1">
          <Link to={`/exercises/${exercise.exercise_id}`} className="block text-xl font-bold leading-tight tracking-tight hover:underline">
            {exercise.exercise_name}
          </Link>
          <p className="mt-1 text-sm text-muted-foreground">
            {[exercise.primary_muscle_group, exercise.equipment_detail ?? exercise.equipment_name].filter(Boolean).join(" · ")}
          </p>
          {exercise.attachment && <p className="text-sm text-muted-foreground">Attachment: {exercise.attachment}</p>}
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            <Badge variant="primary">
              {exercise.target_sets} × {targetText(exercise, exercise.tracking_type)}
            </Badge>
            {exercise.rest_seconds > 0 && (
              <Badge>
                <Timer />
                {restText(exercise.rest_seconds)}
              </Badge>
            )}
            {load && <Badge variant="outline">{load}</Badge>}
            {exercise.unilateral && <Badge variant="outline">Left / right</Badge>}
          </div>
        </div>
      </div>

      <div className="space-y-2 px-4 sm:px-5">
        <div className="flex items-start gap-3 rounded-xl bg-muted/60 p-3 text-sm">
          <History className="mt-0.5 size-[18px] shrink-0 text-muted-foreground" />
          {exercise.previous ? (
            <div className="min-w-0">
              <span className="text-muted-foreground">Last time · {dateShort(exercise.previous.performed_on)}</span>
              <div className="tabular font-semibold">{exercise.previous.summary}</div>
              {exercise.previous.load_type !== exercise.load_type && (
                <div className="text-xs text-warning">Recorded as {loadLabel(exercise.previous.load_type, exercise.previous.pulley_ratio)}</div>
              )}
            </div>
          ) : (
            <span className="text-muted-foreground">First time doing this exercise</span>
          )}
        </div>
        <Suggestion exercise={exercise} onApply={onApplyWeight} />
        {exercise.plan_notes && (
          <div className="flex items-start gap-3 rounded-xl border border-border p-3 text-sm text-muted-foreground">
            <Info className="mt-0.5 size-[18px] shrink-0" />
            <span>{exercise.plan_notes}</span>
          </div>
        )}
      </div>

      {!skipped && (
        <div className="px-2.5 pb-2 pt-3 sm:px-3.5">
          {header && (
            <div className="flex items-center gap-2 px-1.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">
              <div className="w-7 text-center">{header[0]}</div>
              <div className="flex-1 text-center">{header[1]}</div>
              <div className="flex-1 text-center">{header[2]}</div>
              <div className="w-12 text-center">Done</div>
            </div>
          )}
          <div className="space-y-1">
            {sets.map((s) => (
              <SetRow
                key={s.id}
                set={s}
                label={setLabel(s)}
                tracking={exercise.tracking_type}
                load={exercise.load_type}
                weightOptions={exercise.weight_options}
                weightIncrement={exercise.weight_increment}
                onChange={(patch) => onSetChange(s.id, patch)}
              />
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-3 sm:px-5">
        {!skipped && (
          <>
            <Button variant="secondary" size="sm" onClick={onAddSet} disabled={busy}>
              <Plus /> Set
            </Button>
            <Button variant="ghost" size="sm" onClick={onRemoveLastSet} disabled={busy || sets.length === 0}>
              <Minus /> Set
            </Button>
          </>
        )}
        {!skipped && onStartRest && exercise.rest_seconds > 0 && (
          <Button variant="ghost" size="sm" onClick={onStartRest}>
            <Timer /> Rest
          </Button>
        )}
        <div className="ml-auto flex gap-1">
          <Button variant="ghost" size="sm" onClick={() => setShowNotes((v) => !v)} aria-expanded={showNotes}>
            <NotebookPen /> Note
          </Button>
          {onToggleSkip && (
            <Button variant="ghost" size="sm" onClick={onToggleSkip} disabled={busy}>
              {skipped ? <Undo2 /> : <SkipForward />}
              {skipped ? "Unskip" : "Skip"}
            </Button>
          )}
        </div>
        {showNotes && (
          <Textarea
            className="mt-1 min-h-16"
            placeholder="Notes for this exercise (form cues, seat height, how it felt…)"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            onBlur={() => {
              if (notes !== (exercise.notes ?? "")) onNotesSave(notes);
            }}
          />
        )}
      </div>
    </article>
  );
}
