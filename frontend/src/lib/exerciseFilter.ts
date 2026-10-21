import type { Exercise } from "./types";

export interface ExerciseFilter {
  search: string;
  muscle: string | null;
  equipmentId: number | null;
}

export function filterExercises(exercises: Exercise[], f: ExerciseFilter): Exercise[] {
  const terms = f.search.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return exercises.filter((e) => {
    if (f.muscle && e.primary_muscle_group !== f.muscle && !e.secondary_muscles.includes(f.muscle)) return false;
    if (f.equipmentId !== null && e.equipment_id !== f.equipmentId) return false;
    if (terms.length) {
      const haystack = `${e.name} ${e.primary_muscle_group ?? ""} ${e.equipment_detail ?? ""} ${e.attachment ?? ""}`.toLowerCase();
      return terms.every((t) => haystack.includes(t));
    }
    return true;
  });
}

export function muscleGroupsOf(exercises: Exercise[]): string[] {
  const groups = new Set<string>();
  exercises.forEach((e) => {
    if (e.primary_muscle_group) groups.add(e.primary_muscle_group);
  });
  return [...groups].sort();
}
