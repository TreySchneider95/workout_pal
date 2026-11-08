import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProfileGate } from "@/hooks/profile";
import { api } from "@/lib/api";
import { IDLE_SIGN_OUT_MS, isIdle, markActive } from "@/lib/idle";
import { getProfileId, storeProfileId } from "@/lib/profile";
import { queryClient } from "@/lib/queryClient";
import type { Profile, SessionExercise } from "@/lib/types";
import { nextExerciseIndex, timerSecondsFor } from "@/lib/workoutFlow";

type Ex = Pick<SessionExercise, "status" | "sets">;

/** An exercise with `total` sets, the first `done` of them checked off. */
const ex = (total: number, done = 0, status: SessionExercise["status"] = "active"): Ex => ({
  status,
  sets: Array.from({ length: total }, (_, i) => ({
    id: i + 1,
    set_number: i + 1,
    side: null,
    weight: 20,
    repetitions: 8,
    duration_seconds: null,
    distance: null,
    speed: null,
    completed: i < done,
    completed_at: null,
  })),
});

describe("nextExerciseIndex", () => {
  it("moves through the exercises in order during the first round", () => {
    const workout = [ex(2, 1), ex(2), ex(2)];
    expect(nextExerciseIndex(workout, 0)).toBe(1);
    expect(nextExerciseIndex(workout, 1)).toBe(2);
  });

  it("goes back to the top for the next round", () => {
    const workout = [ex(2, 1), ex(2, 1), ex(2, 1)];
    expect(nextExerciseIndex(workout, 2)).toBe(0);
  });

  it("jumps to the first exercise that still has a set left", () => {
    // Exercises 1 and 2 are finished; 3 has a third set.
    const workout = [ex(2, 2), ex(2, 2), ex(3, 2), ex(2, 2)];
    expect(nextExerciseIndex(workout, 3)).toBe(2);
    expect(nextExerciseIndex(workout, 0)).toBe(2);
  });

  it("passes over skipped exercises", () => {
    const workout = [ex(2, 1), ex(2, 0, "skipped"), ex(2, 1)];
    expect(nextExerciseIndex(workout, 0)).toBe(2);
    expect(nextExerciseIndex(workout, 2)).toBe(0);
  });

  it("works for straight sets too", () => {
    const workout = [ex(3, 3), ex(3, 3), ex(3)];
    expect(nextExerciseIndex(workout, 1)).toBe(2);
  });

  it("returns null when nothing else has sets left", () => {
    expect(nextExerciseIndex([ex(2, 2), ex(2, 2)], 1)).toBeNull();
    // Only the current exercise has sets left: finish from here.
    expect(nextExerciseIndex([ex(2, 2), ex(2, 1)], 1)).toBeNull();
    expect(nextExerciseIndex([ex(2)], 0)).toBeNull();
    expect(nextExerciseIndex([], 0)).toBeNull();
  });
});

describe("timerSecondsFor", () => {
  const timed = (durations: (number | null)[], done = 0) => ({
    target_duration_min: 45,
    rest_seconds: 90,
    sets: ex(durations.length, done).sets.map((s, i) => ({ ...s, duration_seconds: durations[i] })),
  });

  it("uses the next set's duration, as adjusted on screen", () => {
    expect(timerSecondsFor(timed([60, 50], 1))).toBe(50);
    expect(timerSecondsFor({ ...timed([1200]), target_duration_min: 1200 })).toBe(1200);
  });

  it("falls back to the planned duration, then rest time, then a minute", () => {
    expect(timerSecondsFor(timed([null]))).toBe(45);
    expect(timerSecondsFor({ ...ex(3), target_duration_min: null, rest_seconds: 90 })).toBe(90);
    expect(timerSecondsFor({ ...ex(3), target_duration_min: null, rest_seconds: 0 })).toBe(60);
  });
});

describe("idle sign-out", () => {
  const profiles = [
    { id: 1, name: "Trey", email: null },
    { id: 2, name: "Abby", email: null },
  ] satisfies Profile[];

  beforeEach(() => {
    localStorage.clear();
    queryClient.clear();
    vi.spyOn(api, "profiles").mockResolvedValue(profiles);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  const renderGate = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ProfileGate>
            <p>Signed in</p>
          </ProfileGate>
        </MemoryRouter>
      </QueryClientProvider>,
    );

  it("knows when the device has been idle for an hour", () => {
    expect(isIdle()).toBe(false); // never used
    markActive(1_000);
    expect(isIdle(1_000 + IDLE_SIGN_OUT_MS - 1)).toBe(false);
    expect(isIdle(1_000 + IDLE_SIGN_OUT_MS)).toBe(true);
  });

  it("asks who's training again after an hour without a touch", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    storeProfileId(1);
    renderGate();
    expect(await screen.findByText("Signed in")).toBeInTheDocument();

    // Touches keep the session alive.
    await act(() => vi.advanceTimersByTimeAsync(IDLE_SIGN_OUT_MS - 60_000));
    act(() => {
      window.dispatchEvent(new Event("pointerdown"));
    });
    await act(() => vi.advanceTimersByTimeAsync(IDLE_SIGN_OUT_MS - 60_000));
    expect(screen.getByText("Signed in")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(2 * 60_000));
    expect(screen.getByText("Who's training?")).toBeInTheDocument();
    expect(getProfileId()).toBeNull();
  });

  it("signs out on load when the device sat unused (screen off, reboot)", async () => {
    storeProfileId(1);
    markActive(Date.now() - IDLE_SIGN_OUT_MS - 1);
    renderGate();
    expect(await screen.findByText("Who's training?")).toBeInTheDocument();
    expect(getProfileId()).toBeNull();
  });

  it("keeps you signed in after a quick reload", async () => {
    storeProfileId(2);
    markActive(Date.now() - 5 * 60_000);
    renderGate();
    expect(await screen.findByText("Signed in")).toBeInTheDocument();
  });
});
