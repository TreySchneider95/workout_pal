import { useQuery } from "@tanstack/react-query";
import { BarChart3, Trophy } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router";

import { EmptyState, PageHeader, StatTile } from "@/components/AppShell";
import { BarTrend, CHART_COLOR, LineTrend } from "@/components/Charts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { api, localDate } from "@/lib/api";
import { compactNumber, dateShort, dateWithWeekday, lb, loadLabel, minutesText } from "@/lib/format";
import type { CalendarDay } from "@/lib/types";
import { cn } from "@/lib/utils";

function ConsistencyGrid({ days }: { days: CalendarDay[] }) {
  const navigate = useNavigate();
  const today = localDate();
  const weeks: CalendarDay[][] = [];
  for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));
  return (
    <div>
      <div className="flex gap-1">
        <div className="mr-1 flex flex-col gap-1 text-[10px] text-subtle">
          {["M", "T", "W", "T", "F", "S", "S"].map((d, i) => (
            <div key={i} className="flex h-5 items-center sm:h-6">
              {d}
            </div>
          ))}
        </div>
        {weeks.map((week) => (
          <div key={week[0].date} className="flex flex-1 flex-col gap-1">
            {week.map((day) => {
              const done = day.session_ids.length > 0;
              const future = day.date > today;
              const missed = !done && day.planned && !future;
              const label = `${dateWithWeekday(day.date)}: ${done ? "workout done" : missed ? "planned, missed" : future ? "upcoming" : "rest"}`;
              return (
                <button
                  key={day.date}
                  title={label}
                  aria-label={label}
                  disabled={!done}
                  onClick={() => done && navigate(`/history/${day.session_ids[0]}`)}
                  className={cn(
                    "h-5 rounded-[4px] sm:h-6",
                    done && "cursor-pointer",
                    !done && missed && "border border-input",
                    !done && !missed && "bg-muted/40",
                    day.date === today && "ring-1 ring-foreground",
                  )}
                  style={done ? { backgroundColor: CHART_COLOR } : undefined}
                />
              );
            })}
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="size-3 rounded-[3px]" style={{ backgroundColor: CHART_COLOR }} /> Workout done
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="size-3 rounded-[3px] border border-input" /> Planned, missed
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="size-3 rounded-[3px] bg-muted/40" /> Rest / upcoming
        </span>
      </div>
    </div>
  );
}

function ExerciseProgressCard() {
  const exercises = useQuery({ queryKey: ["exercises", "enabled"], queryFn: () => api.exercises() });
  const planned = (exercises.data ?? []).filter((e) => e.scheduled_in.length > 0);
  const [selected, setSelected] = React.useState<string>("");
  const id = selected || planned[0]?.id || "";
  const progress = useQuery({ queryKey: ["exercise-progress", id], queryFn: () => api.exerciseProgress(id), enabled: !!id });
  const ex = planned.find((e) => e.id === id);
  const weighted = ex && ["per_dumbbell", "single_dumbbell", "plates_loaded", "added_plates"].includes(ex.load_type);
  const points = progress.data?.points ?? [];
  const data = points.map((p) => ({
    label: dateShort(p.performed_on),
    value: weighted ? p.top_weight : p.total_reps || (p.total_duration ? Math.round(p.total_duration / 60) : null),
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Exercise progress</CardTitle>
        <Select value={id} onChange={(e) => setSelected(e.target.value)} aria-label="Exercise" className="mt-1">
          {planned.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name}
            </option>
          ))}
        </Select>
      </CardHeader>
      <CardContent>
        {points.length ? (
          <>
            <p className="mb-1 text-sm text-muted-foreground">
              {weighted ? `Heaviest completed set (${loadLabel(ex!.load_type, ex!.pulley_ratio)})` : "Total reps / minutes per session"}
            </p>
            <LineTrend data={data} unit={weighted ? "lb" : undefined} />
            <Link to={`/exercises/${id}`} className="mt-2 inline-block text-sm font-medium text-primary hover:underline">
              Full history →
            </Link>
          </>
        ) : (
          <p className="py-8 text-center text-sm text-muted-foreground">No sessions recorded for this exercise yet.</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function AnalyticsPage() {
  const summary = useQuery({ queryKey: ["analytics"], queryFn: api.analytics });

  if (summary.isLoading || !summary.data) {
    return (
      <div className="space-y-3 pt-10">
        <Skeleton className="h-10 w-1/3" />
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-60" />
      </div>
    );
  }
  const s = summary.data;
  const weekLabel = (iso: string) => dateShort(iso);

  return (
    <div>
      <PageHeader title="Stats" subtitle="Your training over the last 12 weeks" />
      {s.total_workouts === 0 ? (
        <EmptyState icon={BarChart3} title="No stats yet">
          Complete your first workout and your progress shows up here.
        </EmptyState>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="This week" value={`${s.workouts_this_week} / ${s.planned_this_week}`} hint="workouts / planned" />
            <StatTile label="Total workouts" value={s.total_workouts} hint={s.current_streak_weeks ? `${s.current_streak_weeks} full week${s.current_streak_weeks === 1 ? "" : "s"} in a row` : undefined} />
            <StatTile label="Total time" value={minutesText(s.total_minutes)} hint={s.average_minutes ? `avg ${s.average_minutes} min` : undefined} />
            <StatTile label="Consistency" value={s.consistency_percent !== null ? `${s.consistency_percent}%` : "–"} hint="planned days done, 8 wks" />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Consistency</CardTitle>
            </CardHeader>
            <CardContent>
              <ConsistencyGrid days={s.calendar} />
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Workouts per week</CardTitle>
                <p className="text-sm text-muted-foreground">Plan: {s.planned_this_week} per week</p>
              </CardHeader>
              <CardContent>
                <BarTrend data={s.weeks.map((w) => ({ label: weekLabel(w.week_start), value: w.workouts, detail: `${minutesText(w.minutes)} total` }))} unit="workouts" />
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Training volume per week</CardTitle>
                <p className="text-sm text-muted-foreground">Weight × reps of completed sets, as recorded</p>
              </CardHeader>
              <CardContent>
                <BarTrend data={s.weeks.map((w) => ({ label: weekLabel(w.week_start), value: Math.round(w.volume) }))} unit="lb" />
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ExerciseProgressCard />
            <Card>
              <CardHeader>
                <CardTitle>Recent personal bests</CardTitle>
                <p className="text-sm text-muted-foreground">Heavier than any previous session</p>
              </CardHeader>
              <CardContent>
                {s.personal_bests.length ? (
                  <ul className="divide-y divide-border">
                    {s.personal_bests.map((pb) => (
                      <li key={`${pb.exercise_id}-${pb.performed_on}`}>
                        <Link to={`/exercises/${pb.exercise_id}`} className="flex items-center gap-3 py-3 hover:opacity-80">
                          <Trophy className="size-5 shrink-0 text-warning" />
                          <div className="min-w-0 flex-1">
                            <div className="truncate font-medium">{pb.exercise_name}</div>
                            <div className="text-sm text-muted-foreground">
                              {dateShort(pb.performed_on)} · was {lb(pb.previous_best)}
                            </div>
                          </div>
                          <div className="tabular shrink-0 text-right">
                            <div className="font-semibold">{lb(pb.weight)}</div>
                            <div className="text-xs text-muted-foreground">× {pb.repetitions ?? "–"}</div>
                          </div>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="py-8 text-center text-sm text-muted-foreground">No new bests yet. They appear when you lift heavier than before.</p>
                )}
              </CardContent>
            </Card>
          </div>
          <p className="text-center text-xs text-subtle">{compactNumber(s.weeks.reduce((n, w) => n + w.volume, 0))} lb total volume in 12 weeks</p>
        </div>
      )}
    </div>
  );
}
