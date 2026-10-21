import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { ExerciseTracker } from "@/components/ExerciseTracker";
import { SetRow } from "@/components/SetRow";
import { Stepper, nextValue } from "@/components/Stepper";
import type { ExerciseSet, SessionExercise } from "@/lib/types";

const set = (patch: Partial<ExerciseSet> = {}): ExerciseSet => ({
  id: 1,
  set_number: 1,
  side: null,
  weight: 20,
  repetitions: 8,
  duration_seconds: null,
  distance: null,
  speed: null,
  completed: false,
  completed_at: null,
  ...patch,
});

describe("Stepper", () => {
  it("steps through the available dumbbells only", () => {
    const dumbbells = [5, 10, 12.5, 15, 20];
    expect(nextValue(12.5, 1, dumbbells, 5, 0, 100)).toBe(15);
    expect(nextValue(12.5, -1, dumbbells, 5, 0, 100)).toBe(10);
    expect(nextValue(20, 1, dumbbells, 5, 0, 100)).toBe(20);
    expect(nextValue(11, 1, dumbbells, 5, 0, 100)).toBe(12.5);
    expect(nextValue(20, 1, null, 2.5, 0, 100)).toBe(22.5);
    expect(nextValue(0, -1, null, 5, 0, 100)).toBe(0);
  });

  it("lets you type a value", async () => {
    const onChange = vi.fn();
    render(<Stepper label="Reps" value={8} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /Reps: 8/ }));
    const input = screen.getByRole("spinbutton", { name: "Reps" });
    await userEvent.clear(input);
    await userEvent.type(input, "11{Enter}");
    expect(onChange).toHaveBeenCalledWith(11);
  });
});

describe("SetRow", () => {
  it("adjusts weight and reps independently and marks the set done", async () => {
    const onChange = vi.fn();
    render(<SetRow set={set()} label="1" tracking="strength" load="per_dumbbell" weightOptions={[15, 20, 25]} weightIncrement={5} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Increase Weight" }));
    expect(onChange).toHaveBeenLastCalledWith({ weight: 25 });
    await userEvent.click(screen.getByRole("button", { name: "Decrease Reps" }));
    expect(onChange).toHaveBeenLastCalledWith({ repetitions: 7 });
    await userEvent.click(screen.getByRole("button", { name: "Mark set 1 complete" }));
    expect(onChange).toHaveBeenLastCalledWith({ completed: true });
  });

  it("can undo a completed set", async () => {
    const onChange = vi.fn();
    render(<SetRow set={set({ completed: true })} label="2L" tracking="strength" load="per_dumbbell" weightOptions={null} weightIncrement={5} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /Set 2L completed/ }));
    expect(onChange).toHaveBeenCalledWith({ completed: false });
  });

  it("shows BW for bodyweight sets without added weight", () => {
    render(<SetRow set={set({ weight: null })} label="1" tracking="bodyweight" load="bodyweight" weightOptions={null} weightIncrement={5} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Added weight: BW/ })).toBeInTheDocument();
  });
});

const exercise = (patch: Partial<SessionExercise> = {}): SessionExercise => ({
  id: 5,
  exercise_id: "EX0001",
  exercise_order: 1,
  status: "active",
  notes: null,
  exercise_name: "Flat dumbbell bench press",
  tracking_type: "strength",
  load_type: "per_dumbbell",
  pulley_ratio: null,
  unilateral: false,
  target_sets: 2,
  target_text: "8-10",
  target_rep_min: 8,
  target_rep_max: 10,
  target_duration_min: null,
  target_duration_max: null,
  suggested_weight: 20,
  recommended_weight: 25,
  suggestion_action: "increase",
  suggestion_reason: "Hit 10+ reps on all 2 sets at 20 lb. Ready for 25 lb",
  rest_seconds: 120,
  plan_notes: null,
  primary_muscle_group: "Chest",
  equipment_name: "Dumbbells",
  equipment_detail: "Dumbbells + adjustable bench",
  attachment: null,
  image_url: null,
  thumb_url: null,
  weight_options: [15, 20, 25],
  weight_increment: 5,
  previous: {
    session_id: 1,
    session_name: "Upper A",
    performed_on: "2026-10-12",
    load_type: "per_dumbbell",
    pulley_ratio: null,
    sets: [],
    summary: "20 lb × 10, 10",
  },
  sets: [set({ id: 1 }), set({ id: 2, set_number: 2 })],
  ...patch,
});

describe("ExerciseTracker", () => {
  const handlers = () => ({
    onSetChange: vi.fn(),
    onAddSet: vi.fn(),
    onRemoveLastSet: vi.fn(),
    onApplyWeight: vi.fn(),
    onToggleSkip: vi.fn(),
    onNotesSave: vi.fn(),
  });

  it("shows targets, last performance and the weight convention", () => {
    render(
      <MemoryRouter>
        <ExerciseTracker exercise={exercise()} {...handlers()} />
      </MemoryRouter>,
    );
    expect(screen.getByText("2 × 8–10 reps")).toBeInTheDocument();
    expect(screen.getByText("20 lb × 10, 10")).toBeInTheDocument();
    expect(screen.getByText("lb per dumbbell")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /no image/ })).toBeInTheDocument();
  });

  it("only changes weight when the suggestion is accepted", async () => {
    const h = handlers();
    render(
      <MemoryRouter>
        <ExerciseTracker exercise={exercise()} {...h} />
      </MemoryRouter>,
    );
    expect(h.onApplyWeight).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Use 25 lb" }));
    expect(h.onApplyWeight).toHaveBeenCalledWith(25);
  });

  it("routes set edits with the set id", async () => {
    const h = handlers();
    render(
      <MemoryRouter>
        <ExerciseTracker exercise={exercise()} {...h} />
      </MemoryRouter>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Mark set 2 complete" }));
    expect(h.onSetChange).toHaveBeenCalledWith(2, { completed: true });
  });

  it("renders left and right rows for unilateral exercises", () => {
    render(
      <MemoryRouter>
        <ExerciseTracker
          exercise={exercise({
            unilateral: true,
            sets: [set({ id: 1, side: "left" }), set({ id: 2, side: "right" })],
          })}
          {...handlers()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("button", { name: "Mark set 1L complete" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark set 1R complete" })).toBeInTheDocument();
  });
});
