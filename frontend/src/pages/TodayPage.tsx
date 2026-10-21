import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarDays, CalendarPlus, CheckCircle2, Clock, Coffee, Dumbbell, History, ListChecks, Play, RotateCcw, Settings, Shuffle, Sparkles } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router";

import { PageHeader } from "@/components/AppShell";
import { ExerciseImage } from "@/components/ExerciseImage";
import { ProfileSwitcher } from "@/components/ProfileSwitcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Progress, Skeleton } from "@/components/ui/misc";
import { useProfile } from "@/hooks/profile";
import { ApiError, api } from "@/lib/api";
import { dateLong, isWeighted, lb, minutesText, relativeDay, targetText } from "@/lib/format";
import { queryClient } from "@/lib/queryClient";
import type { SessionSummary, Template, TemplateChoice } from "@/lib/types";

function useStartWorkout() {
  const navigate = useNavigate();
  return useMutation({
    mutationFn: (templateId: number | null) => api.startSession(templateId),
    onSuccess: (session) => {
      queryClient.setQueryData(["session", session.id], session);
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      navigate(`/workout/${session.id}`);
    },
    onError: (error) => {
      // A workout is already running: go there instead.
      if (error instanceof ApiError && error.status === 409) {
        const active = (error.detail as { active_session_id?: number })?.active_session_id;
        if (active) navigate(`/workout/${active}`);
      }
    },
  });
}

function TemplatePreview({ template }: { template: Template }) {
  return (
    <ul className="divide-y divide-border">
      {template.exercises
        .filter((te) => !te.skipped)
        .map((te, i) => (
          <li key={te.id} className="flex items-center gap-3 py-2.5">
            <span className="tabular w-5 shrink-0 text-center text-sm font-semibold text-subtle">{i + 1}</span>
            <ExerciseImage thumbUrl={te.exercise.thumb_url} imageUrl={te.exercise.image_url} alt={te.exercise.name} className="size-12 shrink-0" />
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium">{te.exercise.name}</div>
              <div className="text-sm text-muted-foreground">
                {te.planned_sets} × {targetText(te, te.exercise.tracking_type)}
                {isWeighted(te.exercise.load_type) && te.suggested_weight !== null ? ` · from ${lb(te.suggested_weight)}` : ""}
              </div>
            </div>
          </li>
        ))}
    </ul>
  );
}

function ActiveCard({ session }: { session: SessionSummary }) {
  const pct = session.total_sets ? (session.completed_sets / session.total_sets) * 100 : 0;
  return (
    <Card className="border-primary/40 bg-gradient-to-br from-primary/10 to-card p-5">
      <Badge variant="primary">In progress</Badge>
      <h2 className="mt-2 text-2xl font-bold tracking-tight">{session.name}</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {session.completed_sets} of {session.total_sets} sets done · {session.exercises_completed}/{session.exercise_count} exercises started
      </p>
      <Progress value={pct} className="mt-4" />
      <Button asChild size="lg" className="mt-5 w-full">
        <Link to={`/workout/${session.id}`}>
          <Play /> Resume workout
        </Link>
      </Button>
    </Card>
  );
}

function LastWorkout({ session }: { session: SessionSummary }) {
  return (
    <Link to={`/history/${session.id}`} className="block">
      <Card className="p-5 transition-colors hover:bg-elevated">
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Last workout</div>
          <ArrowRight className="size-4 text-subtle" />
        </div>
        <div className="mt-2 flex items-baseline justify-between gap-3">
          <h3 className="text-lg font-semibold">{session.name}</h3>
          <span className="shrink-0 text-sm text-muted-foreground">{relativeDay(session.performed_on)}</span>
        </div>
        <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <Clock className="size-4" /> {minutesText(session.duration_minutes)}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <ListChecks className="size-4" /> {session.completed_sets} sets
          </span>
        </div>
        <ul className="mt-3 space-y-1 text-sm">
          {session.exercises
            .filter((e) => e.best)
            .slice(0, 4)
            .map((e) => (
              <li key={e.exercise_id} className="flex justify-between gap-3">
                <span className="truncate text-muted-foreground">{e.exercise_name}</span>
                <span className="tabular shrink-0 font-medium">{e.best}</span>
              </li>
            ))}
        </ul>
      </Card>
    </Link>
  );
}

function NoPlanCard({ name, onStartEmpty, pending }: { name: string; onStartEmpty: () => void; pending: boolean }) {
  return (
    <Card className="p-6 text-center">
      <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-primary-soft">
        <CalendarPlus className="size-7 text-primary" />
      </div>
      <h2 className="mt-4 text-xl font-semibold">No workout plan yet</h2>
      <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
        Have an AI build {name}'s weekly plan, make one yourself from the exercise library, or log a workout as you go.
      </p>
      <div className="mt-5 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <Button asChild size="lg">
          <Link to="/schedule/assistant">
            <Sparkles /> Build with AI
          </Link>
        </Button>
        <Button asChild variant="secondary" size="lg">
          <Link to="/schedule">
            <CalendarPlus /> Make my own
          </Link>
        </Button>
        <Button variant="secondary" size="lg" disabled={pending} onClick={onStartEmpty}>
          <Dumbbell /> Empty workout
        </Button>
      </div>
    </Card>
  );
}

function ChooseWorkoutDialog({
  open,
  onOpenChange,
  templates,
  onPick,
  pending,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  templates: TemplateChoice[];
  onPick: (id: number | null) => void;
  pending: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Choose a workout" description="Your weekly schedule isn't changed.">
        <ul className="space-y-2">
          {templates.map((t) => (
            <li key={t.id}>
              <button
                disabled={pending}
                onClick={() => onPick(t.id)}
                className="flex w-full items-center gap-3 rounded-2xl border border-border p-4 text-left transition-colors hover:bg-muted disabled:opacity-50"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{t.name}</div>
                  <div className="text-sm text-muted-foreground">
                    {t.weekday_name ?? "Unscheduled"} · {t.exercise_count} exercises · ~{minutesText(t.estimated_duration_minutes)}
                  </div>
                </div>
                <Play className="size-5 text-primary" />
              </button>
            </li>
          ))}
          <li>
            <button
              disabled={pending}
              onClick={() => onPick(null)}
              className="flex w-full items-center gap-3 rounded-2xl border border-dashed border-border p-4 text-left transition-colors hover:bg-muted"
            >
              <div className="min-w-0 flex-1">
                <div className="font-semibold">Empty workout</div>
                <div className="text-sm text-muted-foreground">Pick exercises as you go</div>
              </div>
              <Dumbbell className="size-5 text-muted-foreground" />
            </button>
          </li>
        </ul>
      </DialogContent>
    </Dialog>
  );
}

export default function TodayPage() {
  const dashboard = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });
  const { profile } = useProfile();
  const start = useStartWorkout();
  const [chooseOpen, setChooseOpen] = React.useState(false);

  if (dashboard.isLoading || !dashboard.data) {
    return (
      <div className="space-y-4 pt-10">
        <Skeleton className="h-10 w-2/3" />
        <Skeleton className="h-72" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  const d = dashboard.data;
  const today = d.today;
  const noPlan = d.templates.length === 0;
  const totalSets = today?.exercises.filter((e) => !e.skipped).reduce((n, e) => n + e.planned_sets, 0) ?? 0;

  return (
    <div className="space-y-4">
      <PageHeader
        subtitle={dateLong(d.date)}
        title={d.active_session ? "Keep going" : today ? today.name : noPlan ? `Hi, ${profile.name}` : "Rest day"}
        action={
          <>
            {d.program_week && <Badge variant="outline">Week {d.program_week}</Badge>}
            <Button asChild variant="ghost" size="icon" className="lg:hidden" aria-label="Settings">
              <Link to="/settings">
                <Settings />
              </Link>
            </Button>
            <ProfileSwitcher compact className="lg:hidden" />
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-4">
          {d.active_session && <ActiveCard session={d.active_session} />}

          {!d.active_session && today && (
            <Card className="overflow-hidden">
              <div className="p-5 pb-3">
                {d.completed_today && (
                  <Badge variant="success" className="mb-3">
                    <CheckCircle2 /> Done today
                  </Badge>
                )}
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <div className="tabular text-2xl font-bold">~{today.estimated_duration_minutes}</div>
                    <div className="text-xs text-muted-foreground">minutes</div>
                  </div>
                  <div>
                    <div className="tabular text-2xl font-bold">{today.exercise_count}</div>
                    <div className="text-xs text-muted-foreground">exercises</div>
                  </div>
                  <div>
                    <div className="tabular text-2xl font-bold">{totalSets}</div>
                    <div className="text-xs text-muted-foreground">sets</div>
                  </div>
                </div>
              </div>
              <div className="px-5">
                <TemplatePreview template={today} />
              </div>
              <div className="sticky bottom-[calc(4rem+env(safe-area-inset-bottom))] border-t border-border bg-card/95 p-4 backdrop-blur lg:static">
                {d.completed_today ? (
                  <div className="grid grid-cols-2 gap-3">
                    <Button asChild variant="secondary" size="lg">
                      <Link to={`/history/${d.completed_today.id}`}>View workout</Link>
                    </Button>
                    <Button size="lg" variant="secondary" disabled={start.isPending} onClick={() => start.mutate(today.id)}>
                      <RotateCcw /> Again
                    </Button>
                  </div>
                ) : (
                  <Button size="lg" className="w-full text-[17px]" disabled={start.isPending} onClick={() => start.mutate(today.id)}>
                    <Play className="fill-current" /> {start.isPending ? "Starting…" : "Start workout"}
                  </Button>
                )}
              </div>
            </Card>
          )}

          {!d.active_session && noPlan && (
            <NoPlanCard name={profile.name} pending={start.isPending} onStartEmpty={() => start.mutate(null)} />
          )}

          {!d.active_session && !today && !noPlan && (
            <Card className="p-6 text-center">
              <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-muted">
                <Coffee className="size-7 text-muted-foreground" />
              </div>
              <h2 className="mt-4 text-xl font-semibold">Nothing scheduled today</h2>
              <p className="mt-1 text-sm text-muted-foreground">Today is a rest day in your weekly plan.</p>
              <div className="grid grid-cols-1 mt-5 gap-2 sm:grid-cols-2">
                <Button variant="secondary" size="lg" onClick={() => setChooseOpen(true)}>
                  <Shuffle /> Do a workout anyway
                </Button>
                <Button asChild variant="secondary" size="lg">
                  <Link to="/history">
                    <History /> Browse history
                  </Link>
                </Button>
              </div>
            </Card>
          )}

          {!d.active_session && today && (
            <Button variant="ghost" className="w-full text-muted-foreground" onClick={() => setChooseOpen(true)}>
              <Shuffle /> Do a different workout today
            </Button>
          )}
        </div>

        <div className="space-y-4">
          {d.last_session && <LastWorkout session={d.last_session} />}
          {!noPlan && (
            <Link to="/schedule" className="block">
              <Card className="p-5 transition-colors hover:bg-elevated">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">This week</div>
                  <CalendarDays className="size-4 text-subtle" />
                </div>
                <ul className="mt-3 space-y-1.5 text-sm">
                  {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day, i) => {
                    const t = d.templates.find((x) => x.weekday === i);
                    return (
                      <li key={day} className={i === d.weekday ? "flex justify-between font-semibold" : "flex justify-between text-muted-foreground"}>
                        <span>{day}</span>
                        <span>{t?.name ?? "Rest"}</span>
                      </li>
                    );
                  })}
                </ul>
              </Card>
            </Link>
          )}
        </div>
      </div>

      <ChooseWorkoutDialog
        open={chooseOpen}
        onOpenChange={setChooseOpen}
        templates={d.templates}
        pending={start.isPending}
        onPick={(templateId) => start.mutate(templateId)}
      />
    </div>
  );
}
