import type { LoadType, SessionExercise, TemplateExercise, TrackingType } from "./types";

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const WEEKDAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function num(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
}

export function lb(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : `${num(value)} lb`;
}

/** Explains how a recorded weight should be read. Never reinterprets the number. */
export function loadLabel(load: LoadType, pulley: string | null = null): string | null {
  switch (load) {
    case "per_dumbbell":
      return "lb per dumbbell";
    case "single_dumbbell":
      return "lb · one dumbbell";
    case "plates_loaded":
      return pulley ? `lb plates · ${pulley} pulley` : "lb plates loaded";
    case "added_plates":
      return "lb added plates · bar not incl.";
    case "bodyweight":
      return "bodyweight · + added lb";
    default:
      return null;
  }
}

export function isWeighted(load: LoadType): boolean {
  return load === "per_dumbbell" || load === "single_dumbbell" || load === "plates_loaded" || load === "added_plates";
}

export function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export function durationText(seconds: number | null | undefined): string {
  if (!seconds) return "–";
  if (seconds >= 120 && seconds % 60 === 0) return `${seconds / 60} min`;
  if (seconds >= 60) return clock(seconds);
  return `${seconds}s`;
}

export function minutesText(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "–";
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

export function restText(seconds: number): string {
  if (!seconds) return "No rest";
  return seconds % 60 === 0 ? `${seconds / 60}:00` : clock(seconds);
}

type Target = Pick<
  SessionExercise | TemplateExercise,
  "target_text" | "target_rep_min" | "target_rep_max" | "target_duration_min" | "target_duration_max"
>;

export function targetText(t: Target, tracking?: TrackingType): string {
  if (t.target_duration_min !== null) {
    const lo = t.target_duration_min;
    const hi = t.target_duration_max ?? lo;
    if (tracking === "cardio" || lo >= 120) {
      return lo === hi ? `${Math.round(lo / 60)} min` : `${Math.round(lo / 60)}–${Math.round(hi / 60)} min`;
    }
    return lo === hi ? `${lo} sec` : `${lo}–${hi} sec`;
  }
  if (t.target_rep_min !== null) {
    const hi = t.target_rep_max ?? t.target_rep_min;
    const perSide = t.target_text?.includes("/") ? `/${t.target_text.split("/")[1]}` : "";
    return (t.target_rep_min === hi ? `${hi}` : `${t.target_rep_min}–${hi}`) + ` reps${perSide}`;
  }
  return t.target_text ?? "";
}

export function dateLong(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}

export function dateShort(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", ...(sameYear ? {} : { year: "numeric" }) });
}

export function dateWithWeekday(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export function relativeDay(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const then = new Date(y, m - 1, d).getTime();
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const days = Math.round((today - then) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  return dateShort(iso);
}

export function timeOfDay(isoDateTime: string): string {
  return new Date(isoDateTime).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export function compactNumber(value: number): string {
  if (value >= 10_000) return `${Math.round(value / 1000)}k`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(Math.round(value));
}

export const TRACKING_LABEL: Record<TrackingType, string> = {
  strength: "Weight × reps",
  bodyweight: "Bodyweight reps",
  timed: "Timed hold",
  cardio: "Cardio",
};

export const LOAD_LABEL: Record<LoadType, string> = {
  per_dumbbell: "Per dumbbell (one dumbbell's weight)",
  single_dumbbell: "Single dumbbell",
  plates_loaded: "Plate-loaded cable",
  added_plates: "Added plates (Smith, bar excluded)",
  bodyweight: "Bodyweight (+ optional added weight)",
  none: "No load",
};
