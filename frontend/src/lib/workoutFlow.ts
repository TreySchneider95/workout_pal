import type { SessionExercise } from "./types";

/** An exercise still has work to do if it isn't skipped and has an unchecked set. */
export function hasSetsLeft(e: Pick<SessionExercise, "status" | "sets">): boolean {
  return e.status !== "skipped" && e.sets.some((s) => !s.completed);
}

/**
 * Where "Next" should go: the next exercise after `from` that still has sets
 * left, wrapping around to the start. This supports doing workouts in rounds
 * (one set of each exercise, then back to the top for the next set) as well as
 * straight sets: exercises that are finished are passed over, so after the
 * last exercise you land on the first one that still has a set to do.
 *
 * Returns null when nothing else has sets left (only `from` itself, or nothing).
 */
export function nextExerciseIndex(exercises: Pick<SessionExercise, "status" | "sets">[], from: number): number | null {
  const n = exercises.length;
  for (let step = 1; step < n; step++) {
    const i = (from + step) % n;
    if (hasSetsLeft(exercises[i])) return i;
  }
  return null;
}

const DEFAULT_TIMER_SECONDS = 60;

/**
 * How long the on-demand timer runs for the exercise on screen: the duration of
 * the next set to do (cardio, planks...; it may have been adjusted), else the
 * planned duration, else the exercise's rest time, else a minute.
 */
export function timerSecondsFor(
  e: Pick<SessionExercise, "sets" | "target_duration_min" | "rest_seconds">,
): number {
  const next = e.sets.find((s) => !s.completed) ?? e.sets[e.sets.length - 1];
  const duration = next?.duration_seconds || e.target_duration_min;
  if (duration && duration > 0) return duration;
  return e.rest_seconds > 0 ? e.rest_seconds : DEFAULT_TIMER_SECONDS;
}
