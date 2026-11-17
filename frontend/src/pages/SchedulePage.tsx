import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarCheck, CalendarPlus, ChevronRight, Coffee, Images, Plus, Sparkles } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router";

import { EmptyState, PageHeader } from "@/components/AppShell";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ExerciseImage } from "@/components/ExerciseImage";
import { WeekPicker } from "@/components/WeekPicker";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { MAX_PLAN_WEEKS, WEEKDAYS, minutesText } from "@/lib/format";
import { planLengthText, runsInWeek, startDateForWeek, weeksOverlap } from "@/lib/planWeeks";
import { queryClient } from "@/lib/queryClient";
import type { Template } from "@/lib/types";
import { cn } from "@/lib/utils";

function TemplateRow({ template, today, showWeeks }: { template: Template; today: boolean; showWeeks: boolean }) {
  const active = template.exercises.filter((e) => !e.skipped);
  return (
    <Link to={`/schedule/${template.id}`} className="block">
      <Card className={cn("p-4 transition-colors hover:bg-elevated", today && "border-primary/50")}>
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <h3 className="truncate text-lg font-semibold">{template.name}</h3>
              {today && <span className="text-xs font-semibold text-primary">Today</span>}
            </div>
            <p className="text-sm text-muted-foreground">
              {showWeeks && `${template.weeks_text} · `}
              {active.length} exercises · ~{minutesText(template.estimated_duration_minutes)}
              {template.exercises.length > active.length && ` · ${template.exercises.length - active.length} skipped`}
            </p>
          </div>
          <ChevronRight className="size-5 shrink-0 text-subtle" />
        </div>
        <div className="no-scrollbar mt-3 flex gap-1.5 overflow-x-auto">
          {active.map((te) => (
            <ExerciseImage
              key={te.id}
              thumbUrl={te.exercise.thumb_url}
              imageUrl={te.exercise.image_url}
              alt={te.exercise.name}
              className="size-11 shrink-0"
            />
          ))}
        </div>
      </Card>
    </Link>
  );
}

function NewWorkoutDialog({
  open,
  onOpenChange,
  templates,
  planWeeks,
  week,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  templates: Template[];
  planWeeks: number;
  week: number;
}) {
  const navigate = useNavigate();
  const [name, setName] = React.useState("");
  const [weekday, setWeekday] = React.useState<string>("");
  const [weeks, setWeeks] = React.useState<number[] | null>(null);
  const [copyFrom, setCopyFrom] = React.useState<string>("");
  React.useEffect(() => {
    // A new workout starts out in the week being viewed.
    if (open) setWeeks(planWeeks > 1 ? [week] : null);
  }, [open, planWeeks, week]);
  const create = useMutation({
    mutationFn: () =>
      api.createTemplate({
        name: name.trim(),
        weekday: weekday === "" ? null : Number(weekday),
        weeks,
        copy_from_template_id: copyFrom ? Number(copyFrom) : undefined,
      }),
    onSuccess: (t) => {
      void queryClient.invalidateQueries({ queryKey: ["templates"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onOpenChange(false);
      navigate(`/schedule/${t.id}`);
    },
  });
  const onDay = (day: number) => templates.filter((t) => t.weekday === day && weeksOverlap(t.weeks, weeks));
  const occupied = weekday === "" ? [] : onDay(Number(weekday));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New workout" description="Build a workout from your exercise library.">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) create.mutate();
          }}
        >
          <Field label="Name">
            <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Upper C, Arms & Core" />
          </Field>
          {planWeeks > 1 && (
            <Field label="Weeks">
              <WeekPicker planWeeks={planWeeks} value={weeks} onChange={setWeeks} />
            </Field>
          )}
          <Field
            label="Day"
            hint={
              occupied.length
                ? `${occupied.map((t) => t.name).join(" and ")} ${occupied.length > 1 ? "are" : "is"} on ${WEEKDAYS[Number(weekday)]} in those weeks; unscheduled to make room.`
                : undefined
            }
          >
            <Select value={weekday} onChange={(e) => setWeekday(e.target.value)}>
              <option value="">Not scheduled (start it any day)</option>
              {WEEKDAYS.map((d, i) => (
                <option key={d} value={i}>
                  {d}
                  {onDay(i).length ? ` (${onDay(i).map((t) => t.name).join(", ")})` : ""}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Start from">
            <Select value={copyFrom} onChange={(e) => setCopyFrom(e.target.value)}>
              <option value="">Empty workout</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  Copy of {t.name}
                </option>
              ))}
            </Select>
          </Field>
          <Button type="submit" className="w-full" disabled={!name.trim() || create.isPending}>
            Create workout
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PlanLengthSelect({ templates, planWeeks }: { templates: Template[]; planWeeks: number }) {
  const [pending, setPending] = React.useState<number | null>(null);
  const save = useMutation({
    mutationFn: (weeks: number) => api.updateSettings({ plan_weeks: weeks }),
    onSuccess: (s) => {
      queryClient.setQueryData(["settings"], s);
      for (const key of ["templates", "template", "dashboard", "analytics"]) void queryClient.invalidateQueries({ queryKey: [key] });
    },
  });
  const choose = (weeks: number) => {
    // Shortening the plan drops weeks; say what that does to workouts first.
    if (templates.some((t) => t.weeks?.some((w) => w > weeks))) setPending(weeks);
    else save.mutate(weeks);
  };
  const orphaned = pending === null ? [] : templates.filter((t) => t.weeks && t.weekday !== null && t.weeks.every((w) => w > pending));
  return (
    <>
      <Select aria-label="Plan length" className="w-auto" value={planWeeks} disabled={save.isPending} onChange={(e) => choose(Number(e.target.value))}>
        {Array.from({ length: MAX_PLAN_WEEKS }, (_, i) => i + 1).map((n) => (
          <option key={n} value={n}>
            {n === 1 ? "Same every week" : `${n}-week plan`}
          </option>
        ))}
      </Select>
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(o) => !o && setPending(null)}
        title={`Shorten to ${pending === 1 ? "one week" : `${pending} weeks`}?`}
        description={
          `Weeks after week ${pending} are dropped from every workout.` +
          (orphaned.length ? ` ${orphaned.map((t) => t.name).join(", ")} only run${orphaned.length === 1 ? "s" : ""} in those weeks and will be unscheduled.` : "")
        }
        confirmLabel="Shorten plan"
        destructive
        onConfirm={async () => {
          await save.mutateAsync(pending!);
        }}
      />
    </>
  );
}

export default function SchedulePage() {
  const templates = useQuery({ queryKey: ["templates"], queryFn: api.templates });
  const dashboard = useQuery({ queryKey: ["dashboard"], queryFn: api.dashboard });
  const [newOpen, setNewOpen] = React.useState(false);
  const [viewWeek, setViewWeek] = React.useState<number | null>(null);
  const todayIdx = (new Date().getDay() + 6) % 7; // Monday = 0

  const list = templates.data ?? [];
  const planWeeks = dashboard.data?.plan_weeks ?? 1;
  const currentWeek = dashboard.data?.plan_week ?? 1;
  const week = viewWeek !== null && viewWeek <= planWeeks ? viewWeek : currentWeek;
  const isCurrent = week === currentWeek;
  const multiWeek = planWeeks > 1;
  const unscheduled = list.filter((t) => t.weekday === null);
  const missingPictures = new Set(list.flatMap((t) => t.exercises.filter((te) => !te.exercise.image_url).map((te) => te.exercise.id))).size;

  const makeCurrent = useMutation({
    mutationFn: () => api.updateSettings({ program_start_date: startDateForWeek(week) }),
    onSuccess: (s) => {
      queryClient.setQueryData(["settings"], s);
      for (const key of ["templates", "dashboard", "analytics"]) void queryClient.invalidateQueries({ queryKey: [key] });
    },
  });

  return (
    <div>
      <PageHeader
        title="Plan"
        subtitle={
          list.length ? (multiWeek ? `${planLengthText(planWeeks)} · this is week ${currentWeek}` : "Same workouts every week · tap a day to edit") : undefined
        }
        action={
          <>
            <Button asChild size="sm" variant="secondary">
              <Link to="/schedule/assistant">
                <Sparkles /> Change with AI
              </Link>
            </Button>
            <Button size="sm" onClick={() => setNewOpen(true)}>
              <Plus /> New
            </Button>
          </>
        }
      />
      {templates.isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      ) : (
        <div className="space-y-6">
          {!list.length && (
            <EmptyState icon={CalendarPlus} title="No workouts yet">
              <p>Have an AI build a plan for you (weekly, or a program like 6 weeks that changes each week), or create a workout and pick its exercises yourself.</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                <Button asChild>
                  <Link to="/schedule/assistant">
                    <Sparkles /> Build with AI
                  </Link>
                </Button>
                <Button variant="secondary" onClick={() => setNewOpen(true)}>
                  <Plus /> Create a workout
                </Button>
              </div>
            </EmptyState>
          )}
          {list.length > 0 && (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <PlanLengthSelect templates={list} planWeeks={planWeeks} />
                <Button asChild size="sm" variant="ghost">
                  <Link to="/schedule/pictures">
                    <Images /> Exercise pictures
                    {missingPictures > 0 && <Badge variant="warning">{missingPictures} missing</Badge>}
                  </Link>
                </Button>
                {multiWeek && !isCurrent && (
                  <Button size="sm" variant="ghost" disabled={makeCurrent.isPending} onClick={() => makeCurrent.mutate()}>
                    <CalendarCheck /> Make week {week} this week
                  </Button>
                )}
              </div>
              {multiWeek && (
                <div className="no-scrollbar -mx-4 flex gap-2 overflow-x-auto px-4 py-0.5 lg:mx-0 lg:flex-wrap lg:px-0" role="tablist" aria-label="Plan week">
                  {Array.from({ length: planWeeks }, (_, i) => i + 1).map((w) => (
                    <button
                      key={w}
                      role="tab"
                      aria-selected={w === week}
                      onClick={() => setViewWeek(w)}
                      className={cn(
                        "h-9 shrink-0 rounded-full border px-3.5 text-sm font-medium transition-colors",
                        w === week ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card text-muted-foreground hover:text-foreground",
                      )}
                    >
                      Week {w}
                      {w === currentWeek && " · now"}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          <div className="grid grid-cols-1 gap-x-4 gap-y-4 lg:grid-cols-2">
            {WEEKDAYS.map((day, i) => {
              const t = list.find((x) => x.weekday === i && runsInWeek(x.weeks, week));
              const today = isCurrent && i === todayIdx;
              return (
                <section key={day}>
                  <h2 className={cn("mb-1.5 text-sm font-semibold uppercase tracking-wider", today ? "text-primary" : "text-muted-foreground")}>
                    {day}
                  </h2>
                  {t ? (
                    <TemplateRow template={t} today={today} showWeeks={multiWeek} />
                  ) : (
                    <div className="flex h-[5.5rem] items-center gap-3 rounded-2xl border border-dashed border-border px-4 text-muted-foreground">
                      <Coffee className="size-5" /> Rest day
                    </div>
                  )}
                </section>
              );
            })}
          </div>
          {unscheduled.length > 0 && (
            <section>
              <h2 className="mb-1.5 text-sm font-semibold uppercase tracking-wider text-muted-foreground">Not scheduled</h2>
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {unscheduled.map((t) => (
                  <TemplateRow key={t.id} template={t} today={false} showWeeks={false} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
      <NewWorkoutDialog open={newOpen} onOpenChange={setNewOpen} templates={list} planWeeks={planWeeks} week={week} />
    </div>
  );
}
