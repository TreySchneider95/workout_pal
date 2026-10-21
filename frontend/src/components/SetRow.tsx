import { Check, Pause, Play } from "lucide-react";
import * as React from "react";

import { Stepper } from "@/components/Stepper";
import { clock, isWeighted, num } from "@/lib/format";
import type { ExerciseSet, LoadType, SetPatch, TrackingType } from "@/lib/types";
import { cn } from "@/lib/utils";

interface SetRowProps {
  set: ExerciseSet;
  label: string;
  tracking: TrackingType;
  load: LoadType;
  weightOptions: number[] | null;
  weightIncrement: number | null;
  onChange: (patch: SetPatch) => void;
}

export function setLabel(s: Pick<ExerciseSet, "set_number" | "side">): string {
  return `${s.set_number}${s.side === "left" ? "L" : s.side === "right" ? "R" : ""}`;
}

function CompleteButton({ done, onToggle, label }: { done: boolean; onToggle: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={done}
      aria-label={done ? `Set ${label} completed. Tap to undo.` : `Mark set ${label} complete`}
      className={cn(
        "flex size-12 shrink-0 items-center justify-center rounded-xl border-2 transition-all active:scale-90",
        done ? "border-primary bg-primary text-primary-foreground" : "border-input text-subtle hover:border-muted-foreground",
      )}
    >
      <Check className="size-6" strokeWidth={3} />
    </button>
  );
}

function SetNumber({ label, done }: { label: string; done: boolean }) {
  return (
    <div
      className={cn(
        "tabular flex w-7 shrink-0 items-center justify-center text-sm font-bold",
        done ? "text-primary" : "text-muted-foreground",
      )}
    >
      {label}
    </div>
  );
}

/** Count-up stopwatch that writes the elapsed time into the set when stopped. */
function Stopwatch({ onStop }: { onStop: (seconds: number) => void }) {
  const [startedAt, setStartedAt] = React.useState<number | null>(null);
  const [now, setNow] = React.useState(Date.now());
  React.useEffect(() => {
    if (startedAt === null) return;
    const id = window.setInterval(() => setNow(Date.now()), 200);
    return () => window.clearInterval(id);
  }, [startedAt]);
  const running = startedAt !== null;
  return (
    <button
      type="button"
      onClick={() => {
        if (running) {
          onStop(Math.round((Date.now() - startedAt) / 1000));
          setStartedAt(null);
        } else {
          setStartedAt(Date.now());
          setNow(Date.now());
        }
      }}
      className={cn(
        "tabular flex h-12 w-[4.5rem] shrink-0 items-center justify-center gap-1 rounded-xl text-sm font-semibold transition-colors",
        running ? "bg-warning text-black" : "bg-muted text-foreground",
      )}
      aria-label={running ? "Stop stopwatch" : "Start stopwatch"}
    >
      {running ? (
        <>
          <Pause className="size-4" />
          {clock((now - startedAt) / 1000)}
        </>
      ) : (
        <>
          <Play className="size-4" />
          Time
        </>
      )}
    </button>
  );
}

export function SetRow({ set, label, tracking, load, weightOptions, weightIncrement, onChange }: SetRowProps) {
  const done = set.completed;
  const weighted = isWeighted(load);
  const dim = !done;
  const toggle = () => onChange({ completed: !done });
  const rowClass = cn(
    "flex items-center gap-2 rounded-2xl px-1.5 py-1.5 transition-colors",
    done && "bg-primary-soft",
  );

  if (tracking === "cardio") {
    return (
      <div className={cn(rowClass, "flex-col items-stretch gap-2 p-2")}>
        <div className="grid grid-cols-3 gap-2">
          <Stepper
            label="Duration"
            unit="min"
            value={set.duration_seconds === null ? null : Math.round(set.duration_seconds / 60)}
            onChange={(v) => onChange({ duration_seconds: v * 60 })}
            max={360}
            dim={dim}
            compact
          />
          <Stepper
            label="Distance"
            unit="miles"
            value={set.distance}
            step={0.1}
            decimals
            max={100}
            onChange={(v) => onChange({ distance: v })}
            format={(v) => (v === null ? "–" : v.toFixed(1))}
            dim={dim}
            compact
          />
          <Stepper
            label="Speed"
            unit="mph"
            value={set.speed}
            step={0.1}
            decimals
            max={25}
            onChange={(v) => onChange({ speed: v })}
            format={(v) => (v === null ? "–" : v.toFixed(1))}
            dim={dim}
            compact
          />
        </div>
        <button
          type="button"
          onClick={toggle}
          aria-pressed={done}
          className={cn(
            "flex h-12 items-center justify-center gap-2 rounded-xl border-2 font-semibold transition-colors",
            done ? "border-primary bg-primary text-primary-foreground" : "border-input text-muted-foreground",
          )}
        >
          <Check className="size-5" strokeWidth={3} />
          {done ? "Done" : "Mark done"}
        </button>
      </div>
    );
  }

  if (tracking === "timed") {
    return (
      <div className={rowClass}>
        <SetNumber label={label} done={done} />
        {weighted && (
          <Stepper
            label="Weight"
            unit="lb"
            value={set.weight}
            options={weightOptions}
            step={weightIncrement ?? 5}
            decimals
            onChange={(v) => onChange({ weight: v })}
            dim={dim}
            className="flex-1"
          />
        )}
        <Stepper
          label="Duration"
          unit="sec"
          value={set.duration_seconds}
          step={5}
          max={3600}
          onChange={(v) => onChange({ duration_seconds: v })}
          format={(v) => (v === null ? "–" : v >= 60 ? clock(v) : String(v))}
          dim={dim}
          className="flex-1"
        />
        <Stopwatch onStop={(s) => onChange({ duration_seconds: s })} />
        <CompleteButton done={done} onToggle={toggle} label={label} />
      </div>
    );
  }

  return (
    <div className={rowClass}>
      <SetNumber label={label} done={done} />
      <Stepper
        label={weighted ? "Weight" : "Added weight"}
        unit={weighted ? "lb" : "+lb"}
        value={set.weight}
        options={weighted ? weightOptions : null}
        step={weightIncrement ?? 5}
        decimals
        onChange={(v) => onChange({ weight: v })}
        format={(v) => (!weighted && !v ? "BW" : num(v))}
        dim={dim}
        className="flex-1"
      />
      <Stepper
        label="Reps"
        unit="reps"
        value={set.repetitions}
        max={500}
        onChange={(v) => onChange({ repetitions: v })}
        dim={dim}
        className="flex-1"
      />
      <CompleteButton done={done} onToggle={toggle} label={label} />
    </div>
  );
}
