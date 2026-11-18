import { localDate } from "./api";

/** Plans repeat every `plan_weeks` weeks; a workout's `weeks` lists the plan weeks it runs in (null = every week). */

export function runsInWeek(weeks: number[] | null, week: number): boolean {
  return !weeks || weeks.includes(week);
}

export function weeksOverlap(a: number[] | null, b: number[] | null): boolean {
  if (!a || !b) return true;
  return a.some((w) => b.includes(w));
}

/** Plan start date that makes this calendar week (Monday–Sunday) week `week` of the plan. */
export function startDateForWeek(week: number, today: Date = new Date()): string {
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7) - 7 * (week - 1));
  return localDate(monday);
}

/** "every week", "week 2", "weeks 1–3" or "weeks 1, 3, 5" (like the server's weeks_text, lower case). */
export function weeksText(weeks: number[] | null): string {
  if (!weeks?.length) return "every week";
  const ws = [...new Set(weeks)].sort((a, b) => a - b);
  if (ws.length === 1) return `week ${ws[0]}`;
  if (ws[ws.length - 1] - ws[0] === ws.length - 1) return `weeks ${ws[0]}–${ws[ws.length - 1]}`;
  return `weeks ${ws.join(", ")}`;
}

/** What happens to `occupant` when a workout running in `weeks` takes its day (and it can't swap days):
 *  it keeps the weeks the new workout doesn't use, or is unscheduled. */
export function remainingWeeks(occupant: number[] | null, weeks: number[] | null, planWeeks: number): number[] | null | "none" {
  if (planWeeks <= 1) return "none";
  const all = Array.from({ length: planWeeks }, (_, i) => i + 1);
  const taken = weeks ?? all;
  const left = (occupant ?? all).filter((w) => !taken.includes(w));
  if (!left.length) return "none";
  return left.length === planWeeks ? null : left;
}

export function planLengthText(planWeeks: number): string {
  return planWeeks > 1 ? `${planWeeks}-week plan` : "Same every week";
}
