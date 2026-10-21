import { Pause, Play, X } from "lucide-react";

import { useRestTimer } from "@/hooks/restTimer";
import { clock } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Floating, non-blocking rest countdown. */
export function RestTimerBar() {
  const timer = useRestTimer();
  if (!timer.state) return null;
  const { remaining, running, finished, state } = timer;
  const paused = !running && !finished;
  const progress = state.total ? 1 - remaining / state.total : 1;

  return (
    <div
      className="pointer-events-none fixed inset-x-0 z-40 flex justify-center px-3 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] lg:bottom-6 lg:left-64"
      role="timer"
      aria-live="polite"
    >
      <div
        className={cn(
          "pointer-events-auto relative flex w-full max-w-md items-center gap-2 overflow-hidden rounded-2xl border p-2 pl-4 shadow-2xl shadow-black/60 backdrop-blur animate-slide-up",
          finished ? "border-primary bg-primary text-primary-foreground" : "border-border bg-elevated/95",
        )}
      >
        {!finished && (
          <div className="absolute inset-x-0 bottom-0 h-1 bg-muted">
            <div className="h-full bg-primary transition-[width] duration-300 ease-linear" style={{ width: `${progress * 100}%` }} />
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className={cn("truncate text-xs font-medium uppercase tracking-wide", finished ? "text-primary-foreground/80" : "text-muted-foreground")}>
            {finished ? "Rest over" : paused ? "Paused" : state.label}
          </div>
          <div className="tabular text-3xl font-bold leading-none tracking-tight">{finished ? "Go!" : clock(remaining)}</div>
        </div>
        {!finished && (
          <>
            <button
              className="h-12 rounded-xl px-3 text-sm font-semibold text-muted-foreground hover:bg-muted active:scale-95"
              onClick={() => timer.add(-15)}
              aria-label="Subtract 15 seconds"
            >
              −15
            </button>
            <button
              className="h-12 rounded-xl px-3 text-sm font-semibold text-muted-foreground hover:bg-muted active:scale-95"
              onClick={() => timer.add(15)}
              aria-label="Add 15 seconds"
            >
              +15
            </button>
            <button
              className="flex size-12 items-center justify-center rounded-xl bg-muted active:scale-95"
              onClick={paused ? timer.resume : timer.pause}
              aria-label={paused ? "Resume timer" : "Pause timer"}
            >
              {paused ? <Play className="size-5" /> : <Pause className="size-5" />}
            </button>
          </>
        )}
        <button
          className={cn(
            "flex size-12 items-center justify-center rounded-xl active:scale-95",
            finished ? "bg-primary-foreground/10" : "hover:bg-muted",
          )}
          onClick={timer.stop}
          aria-label={finished ? "Dismiss" : "Skip rest"}
        >
          <X className="size-5" />
        </button>
      </div>
    </div>
  );
}
