import { localDate } from "./api";

/** Plans repeat every `plan_weeks` weeks; a workout's `weeks` lists the plan weeks it runs in (null = every week). */

export function runsInWeek(weeks: number[] | null, week: number): boolean {
  return !weeks || weeks.includes(week);
}

export function weeksOverlap(a: number[] | null, b: number[] | null): boolean {
  if (!a || !b) return true;
  return a.some((w) => b.includes(w));
}

/** Program start date that makes this calendar week (Monday–Sunday) week `week` of the plan. */
export function startDateForWeek(week: number, today: Date = new Date()): string {
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7) - 7 * (week - 1));
  return localDate(monday);
}

export function planLengthText(planWeeks: number): string {
  return planWeeks > 1 ? `${planWeeks}-week plan` : "Same every week";
}
