import { useMutation, useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/AppShell";
import { Stepper } from "@/components/Stepper";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { useProfile } from "@/hooks/profile";
import { api } from "@/lib/api";
import { queryClient } from "@/lib/queryClient";
import type { AppSettings, Equipment } from "@/lib/types";

function Row({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div className="min-w-0">
        <div className="font-medium">{title}</div>
        {description && <div className="text-sm text-muted-foreground">{description}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function ProfileCard() {
  const { profile } = useProfile();
  const status = useQuery({ queryKey: ["assistant-status"], queryFn: api.assistantStatus });
  const [email, setEmail] = React.useState(profile.email ?? "");
  const save = useMutation({
    mutationFn: () => api.updateProfile(profile.id, { email: email.trim() || null }),
    onSuccess: () => {
      toast.success("Email saved");
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
      void queryClient.invalidateQueries({ queryKey: ["assistant-status"] });
    },
  });
  const dirty = email.trim() !== (profile.email ?? "");

  return (
    <Card>
      <CardHeader>
        <CardTitle>{profile.name}</CardTitle>
        <CardDescription>Plan, history and these settings are {profile.name}'s own. Switch person from the avatar on Today.</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <Field
            label="Email"
            hint={
              status.data && !status.data.email_enabled
                ? "Where AI plan prompts are sent. Email also needs to be set up on the server (see the README)."
                : "Where AI plan prompts are sent."
            }
          >
            <div className="flex gap-2">
              <Input type="email" inputMode="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
              <Button type="submit" variant="secondary" disabled={!dirty || save.isPending}>
                Save
              </Button>
            </div>
          </Field>
        </form>
      </CardContent>
    </Card>
  );
}

function parseWeights(text: string): number[] | null {
  const values = text
    .split(/[,\s]+/)
    .filter(Boolean)
    .map(Number);
  if (values.some((v) => Number.isNaN(v) || v < 0)) return null;
  return [...new Set(values)].sort((a, b) => a - b);
}

function EquipmentRow({ equipment }: { equipment: Equipment }) {
  const usesList = equipment.equipment_type === "dumbbell";
  const [weights, setWeights] = React.useState((equipment.available_weights ?? []).join(", "));
  const [increment, setIncrement] = React.useState(equipment.weight_increment?.toString() ?? "");
  const save = useMutation({
    mutationFn: () =>
      api.updateEquipment(
        equipment.id,
        usesList ? { available_weights: parseWeights(weights) } : { weight_increment: increment ? Number(increment) : null },
      ),
    onSuccess: () => {
      toast.success(`${equipment.name} saved`);
      void queryClient.invalidateQueries({ queryKey: ["equipment"] });
      void queryClient.invalidateQueries({ queryKey: ["exercises"] });
    },
  });
  if (equipment.equipment_type === "cardio") return null;
  const invalid = usesList ? parseWeights(weights) === null : increment !== "" && !(Number(increment) > 0);

  return (
    <div className="space-y-2 py-4">
      <div>
        <div className="font-medium">{equipment.name}</div>
        {equipment.notes && <div className="text-sm text-muted-foreground">{equipment.notes}</div>}
      </div>
      <div className="flex gap-2">
        {usesList ? (
          <Input value={weights} onChange={(e) => setWeights(e.target.value)} aria-label={`${equipment.name} available weights`} placeholder="5, 10, 12.5, 15…" />
        ) : (
          <Input
            type="number"
            inputMode="decimal"
            step="any"
            value={increment}
            onChange={(e) => setIncrement(e.target.value)}
            aria-label={`${equipment.name} weight increment`}
            placeholder="Increment (lb)"
          />
        )}
        <Button variant="secondary" disabled={invalid || save.isPending} onClick={() => save.mutate()}>
          Save
        </Button>
      </div>
      <p className="text-xs text-subtle">
        {usesList ? "Dumbbell weights you own (lb per dumbbell). Suggestions only use these." : "Smallest weight jump you can add (lb)."}
      </p>
    </div>
  );
}

export default function SettingsPage() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const equipment = useQuery({ queryKey: ["equipment"], queryFn: api.equipment });
  const update = useMutation({
    mutationFn: (body: Partial<AppSettings> & { clear_program_start_date?: boolean }) => api.updateSettings(body),
    onSuccess: (s) => {
      queryClient.setQueryData(["settings"], s);
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["templates"] });
    },
  });

  if (!settings.data) {
    return (
      <div className="space-y-3 pt-10">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-48" />
      </div>
    );
  }
  const s = settings.data;

  return (
    <div className="space-y-4">
      <PageHeader title="Settings" />

      <ProfileCard />

      <Card>
        <CardHeader>
          <CardTitle>Program</CardTitle>
          <CardDescription>The first weeks use fewer sets (from the plan's “weeks 1–2” column).</CardDescription>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          <div className="pb-3">
            <Field label="Program start date" hint="Set automatically when you start your first workout.">
              <div className="flex gap-2">
                <Input
                  type="date"
                  value={s.program_start_date ?? ""}
                  onChange={(e) =>
                    e.target.value ? update.mutate({ program_start_date: e.target.value }) : update.mutate({ clear_program_start_date: true })
                  }
                />
              </div>
            </Field>
          </div>
          <Row title="Ramp-in weeks" description="Weeks that use the lower set count">
            <Stepper label="Ramp-in weeks" value={s.ramp_weeks} min={0} max={12} onChange={(v) => update.mutate({ ramp_weeks: v })} className="w-36" />
          </Row>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Rest timer</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          <Row title="Start automatically" description="After you tick off a set">
            <Switch checked={s.rest_timer_auto_start} onCheckedChange={(v) => update.mutate({ rest_timer_auto_start: v })} />
          </Row>
          <Row title="Sound" description="Chime when rest is over (vibrates too, where supported)">
            <Switch checked={s.rest_timer_sound} onCheckedChange={(v) => update.mutate({ rest_timer_sound: v })} />
          </Row>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Weight suggestions</CardTitle>
          <CardDescription>
            When every set reaches the top of the rep range, the next available weight is suggested. Suggestions are never applied without your tap.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Row title="Suggest a lighter weight" description="When average reps fall this many below the range">
            <Stepper
              label="Rep drop threshold"
              value={s.progression_drop_threshold}
              min={1}
              max={10}
              onChange={(v) => update.mutate({ progression_drop_threshold: v })}
              className="w-36"
            />
          </Row>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Equipment</CardTitle>
          <CardDescription>Weight steps your equipment supports. All weights are in pounds.</CardDescription>
        </CardHeader>
        <CardContent className="divide-y divide-border pt-0">
          {equipment.data?.map((eq) => <EquipmentRow key={`${eq.id}-${eq.available_weights?.join()}-${eq.weight_increment}`} equipment={eq} />)}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Data</CardTitle>
          <CardDescription>
            Your workouts live in a SQLite database in the project's <code className="text-foreground">data/</code> folder. See the README to back it up or re-import
            your plan.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="secondary" size="sm">
            <a href="/api/docs" target="_blank" rel="noreferrer">
              API documentation <ExternalLink />
            </a>
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
