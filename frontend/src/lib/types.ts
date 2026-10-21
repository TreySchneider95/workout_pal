// Mirrors backend/app/schemas.py

export type TrackingType = "strength" | "bodyweight" | "timed" | "cardio";
export type LoadType =
  | "per_dumbbell"
  | "single_dumbbell"
  | "plates_loaded"
  | "added_plates"
  | "bodyweight"
  | "none";
export type Side = "left" | "right";
export type SuggestionAction = "start" | "plan" | "increase" | "maintain" | "decrease" | "none";

export interface Profile {
  id: number;
  name: string;
  email: string | null;
}

export interface AssistantStatus {
  email_enabled: boolean;
  email: string | null;
}

export type ChangeStatus = "added" | "removed" | "changed" | "unchanged";

export interface PlanDiffExercise {
  exercise_id: string;
  exercise_name: string;
  status: ChangeStatus;
  changes: string[];
  sets: number;
  reps_or_duration: string;
  weight: number | null;
}

export interface PlanDiffWorkout {
  name: string;
  day: string | null;
  previous_day: string | null;
  status: ChangeStatus;
  notes: string[];
  exercises: PlanDiffExercise[];
}

export interface PlanPreview {
  ok: boolean;
  summary: string | null;
  errors: string[];
  warnings: string[];
  workouts: PlanDiffWorkout[];
}

export interface PlanRevision {
  id: number;
  created_at: string;
  source: "document" | "undo";
  summary: string | null;
  undone_at: string | null;
  can_undo: boolean;
}

export interface Equipment {
  id: number;
  slug: string;
  name: string;
  equipment_type: string;
  weight_increment: number | null;
  available_weights: number[] | null;
  notes: string | null;
}

export interface Exercise {
  id: string;
  name: string;
  primary_muscle_group: string | null;
  secondary_muscles: string[];
  equipment_id: number | null;
  equipment_name: string | null;
  equipment_detail: string | null;
  attachment: string | null;
  tracking_type: TrackingType;
  load_type: LoadType;
  pulley_ratio: string | null;
  unilateral: boolean;
  starting_weight: number | null;
  image_url: string | null;
  thumb_url: string | null;
  notes: string | null;
  enabled: boolean;
  is_custom: boolean;
  weight_options: number[] | null;
  weight_increment: number | null;
  scheduled_in: string[];
}

export type ExerciseInput = Partial<
  Pick<
    Exercise,
    | "name"
    | "primary_muscle_group"
    | "secondary_muscles"
    | "equipment_id"
    | "equipment_detail"
    | "attachment"
    | "tracking_type"
    | "load_type"
    | "pulley_ratio"
    | "unilateral"
    | "starting_weight"
    | "notes"
    | "enabled"
  >
>;

export interface ExerciseBrief {
  id: string;
  name: string;
  primary_muscle_group: string | null;
  tracking_type: TrackingType;
  load_type: LoadType;
  pulley_ratio: string | null;
  unilateral: boolean;
  thumb_url: string | null;
  image_url: string | null;
  enabled: boolean;
  equipment_name: string | null;
}

export interface TemplateExercise {
  id: number;
  exercise: ExerciseBrief;
  exercise_order: number;
  ramp_sets: number | null;
  target_sets: number;
  planned_sets: number;
  target_text: string | null;
  target_rep_min: number | null;
  target_rep_max: number | null;
  target_duration_min: number | null;
  target_duration_max: number | null;
  per_side: boolean;
  suggested_weight: number | null;
  default_rest_seconds: number;
  notes: string | null;
  skipped: boolean;
}

export interface Template {
  id: number;
  name: string;
  weekday: number | null;
  weekday_name: string | null;
  estimated_duration_minutes: number;
  estimated_duration_override: number | null;
  notes: string | null;
  exercise_count: number;
  exercises: TemplateExercise[];
}

export interface TemplateExerciseInput {
  target_sets?: number;
  ramp_sets?: number | null;
  target_rep_min?: number | null;
  target_rep_max?: number | null;
  target_duration_min?: number | null;
  target_duration_max?: number | null;
  per_side?: boolean;
  suggested_weight?: number | null;
  default_rest_seconds?: number;
  notes?: string | null;
  skipped?: boolean;
}

export interface ExerciseSet {
  id: number;
  set_number: number;
  side: Side | null;
  weight: number | null;
  repetitions: number | null;
  duration_seconds: number | null;
  distance: number | null;
  speed: number | null;
  completed: boolean;
  completed_at: string | null;
}

export type SetPatch = Partial<
  Pick<ExerciseSet, "weight" | "repetitions" | "duration_seconds" | "distance" | "speed" | "completed">
>;

export interface PreviousPerformance {
  session_id: number;
  session_name: string;
  performed_on: string;
  load_type: LoadType;
  pulley_ratio: string | null;
  sets: ExerciseSet[];
  summary: string;
}

export interface SessionExercise {
  id: number;
  exercise_id: string;
  exercise_order: number;
  status: "active" | "skipped";
  notes: string | null;
  exercise_name: string;
  tracking_type: TrackingType;
  load_type: LoadType;
  pulley_ratio: string | null;
  unilateral: boolean;
  target_sets: number;
  target_text: string | null;
  target_rep_min: number | null;
  target_rep_max: number | null;
  target_duration_min: number | null;
  target_duration_max: number | null;
  suggested_weight: number | null;
  recommended_weight: number | null;
  suggestion_action: SuggestionAction | null;
  suggestion_reason: string | null;
  rest_seconds: number;
  plan_notes: string | null;
  primary_muscle_group: string | null;
  equipment_name: string | null;
  equipment_detail: string | null;
  attachment: string | null;
  image_url: string | null;
  thumb_url: string | null;
  weight_options: number[] | null;
  weight_increment: number | null;
  previous: PreviousPerformance | null;
  sets: ExerciseSet[];
}

export interface WorkoutSession {
  id: number;
  workout_template_id: number | null;
  name: string;
  performed_on: string;
  program_week: number | null;
  started_at: string;
  completed_at: string | null;
  status: "in_progress" | "completed";
  notes: string | null;
  completed_sets: number;
  total_sets: number;
  exercises: SessionExercise[];
}

export interface SessionExerciseSummary {
  exercise_id: string;
  exercise_name: string;
  status: string;
  load_type: LoadType;
  completed_sets: number;
  best: string | null;
}

export interface SessionSummary {
  id: number;
  workout_template_id: number | null;
  name: string;
  performed_on: string;
  started_at: string;
  completed_at: string | null;
  duration_minutes: number | null;
  status: "in_progress" | "completed";
  notes: string | null;
  exercise_count: number;
  exercises_completed: number;
  completed_sets: number;
  total_sets: number;
  volume: number;
  exercises: SessionExerciseSummary[];
}

export interface TemplateChoice {
  id: number;
  name: string;
  weekday: number | null;
  weekday_name: string | null;
  exercise_count: number;
  estimated_duration_minutes: number;
}

export interface Dashboard {
  date: string;
  weekday: number;
  weekday_name: string;
  program_week: number | null;
  today: Template | null;
  active_session: SessionSummary | null;
  last_session: SessionSummary | null;
  completed_today: SessionSummary | null;
  templates: TemplateChoice[];
}

export interface HistoryPage {
  total: number;
  items: SessionSummary[];
}

export interface AppSettings {
  program_start_date: string | null;
  ramp_weeks: number;
  rest_timer_auto_start: boolean;
  rest_timer_sound: boolean;
  progression_drop_threshold: number;
}

export interface ExerciseProgressPoint {
  performed_on: string;
  session_id: number;
  top_weight: number | null;
  best_reps: number | null;
  total_reps: number;
  volume: number;
  total_duration: number | null;
  total_distance: number | null;
}

export interface ExerciseHistoryEntry {
  session_id: number;
  session_name: string;
  performed_on: string;
  load_type: LoadType;
  pulley_ratio: string | null;
  sets: ExerciseSet[];
  top_weight: number | null;
  total_reps: number;
  volume: number;
}

export interface ExerciseProgress {
  exercise_id: string;
  sessions: number;
  best_weight: number | null;
  best_weight_reps: number | null;
  best_weight_date: string | null;
  total_volume: number;
  total_reps: number;
  points: ExerciseProgressPoint[];
  history: ExerciseHistoryEntry[];
}

export interface WeekBucket {
  week_start: string;
  workouts: number;
  planned: number;
  minutes: number;
  volume: number;
}

export interface PersonalBest {
  exercise_id: string;
  exercise_name: string;
  performed_on: string;
  weight: number;
  repetitions: number | null;
  previous_best: number | null;
  load_type: LoadType;
}

export interface CalendarDay {
  date: string;
  session_ids: number[];
  planned: boolean;
}

export interface AnalyticsSummary {
  workouts_this_week: number;
  planned_this_week: number;
  total_workouts: number;
  total_minutes: number;
  average_minutes: number | null;
  consistency_percent: number | null;
  current_streak_weeks: number;
  weeks: WeekBucket[];
  personal_bests: PersonalBest[];
  calendar: CalendarDay[];
}
