import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarPlus, ChevronRight, Coffee, Plus, Sparkles } from "lucide-react";
import * as React from "react";
import { Link, useNavigate } from "react-router";

import { EmptyState, PageHeader } from "@/components/AppShell";
import { ExerciseImage } from "@/components/ExerciseImage";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { WEEKDAYS, minutesText } from "@/lib/format";
import { queryClient } from "@/lib/queryClient";
import type { Template } from "@/lib/types";
import { cn } from "@/lib/utils";

function TemplateRow({ template, today }: { template: Template; today: boolean }) {
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

function NewWorkoutDialog({ open, onOpenChange, templates }: { open: boolean; onOpenChange: (o: boolean) => void; templates: Template[] }) {
  const navigate = useNavigate();
  const [name, setName] = React.useState("");
  const [weekday, setWeekday] = React.useState<string>("");
  const [copyFrom, setCopyFrom] = React.useState<string>("");
  const create = useMutation({
    mutationFn: () =>
      api.createTemplate({
        name: name.trim(),
        weekday: weekday === "" ? null : Number(weekday),
        copy_from_template_id: copyFrom ? Number(copyFrom) : undefined,
      }),
    onSuccess: (t) => {
      void queryClient.invalidateQueries({ queryKey: ["templates"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onOpenChange(false);
      navigate(`/schedule/${t.id}`);
    },
  });
  const occupied = templates.find((t) => weekday !== "" && t.weekday === Number(weekday));

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
          <Field label="Day" hint={occupied ? `${occupied.name} is on ${WEEKDAYS[occupied.weekday!]}; it will be unscheduled (swapped out).` : undefined}>
            <Select value={weekday} onChange={(e) => setWeekday(e.target.value)}>
              <option value="">Not scheduled (start it any day)</option>
              {WEEKDAYS.map((d, i) => (
                <option key={d} value={i}>
                  {d}
                  {templates.find((t) => t.weekday === i) ? ` (${templates.find((t) => t.weekday === i)!.name})` : ""}
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

export default function SchedulePage() {
  const templates = useQuery({ queryKey: ["templates"], queryFn: api.templates });
  const [newOpen, setNewOpen] = React.useState(false);
  const todayIdx = (new Date().getDay() + 6) % 7; // Monday = 0

  const list = templates.data ?? [];
  const unscheduled = list.filter((t) => t.weekday === null);

  return (
    <div>
      <PageHeader
        title="Weekly plan"
        subtitle={list.length ? "Tap a day to edit its workout" : undefined}
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
              <p>Have an AI build a plan for you, or create a workout and pick its exercises yourself.</p>
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
          <div className="grid grid-cols-1 gap-x-4 gap-y-4 lg:grid-cols-2">
            {WEEKDAYS.map((day, i) => {
              const t = list.find((x) => x.weekday === i);
              return (
                <section key={day}>
                  <h2 className={cn("mb-1.5 text-sm font-semibold uppercase tracking-wider", i === todayIdx ? "text-primary" : "text-muted-foreground")}>
                    {day}
                  </h2>
                  {t ? (
                    <TemplateRow template={t} today={i === todayIdx} />
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
                  <TemplateRow key={t.id} template={t} today={false} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
      <NewWorkoutDialog open={newOpen} onOpenChange={setNewOpen} templates={list} />
    </div>
  );
}
