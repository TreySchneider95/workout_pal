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
