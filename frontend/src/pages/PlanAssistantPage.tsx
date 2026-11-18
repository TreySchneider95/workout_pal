import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Check, ChevronLeft, Copy, Download, FileUp, Mail, Sparkles, Undo2 } from "lucide-react";
import * as React from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useProfile } from "@/hooks/profile";
import { api } from "@/lib/api";
import { copyText, downloadText } from "@/lib/clipboard";
import { planLengthText } from "@/lib/planWeeks";
import { queryClient } from "@/lib/queryClient";
import type { ChangeStatus, PlanDiffWorkout, PlanPreview, PlanRevision } from "@/lib/types";
import { cn } from "@/lib/utils";

const EXAMPLES = [
  "Build me a 6-week plan that gets harder each week",
  "Add a lighter deload week every 4th week",
  "Add more core work",
  "Keep every workout under 45 minutes",
  "My shoulder is sore. Swap out anything overhead for now",
  "I'm hitting the top of my rep ranges. Make it harder",
  "Move Friday's workout to Sunday",
];

const REFRESH_AFTER_PLAN_CHANGE = ["templates", "template", "dashboard", "exercises", "plan-revisions", "settings", "analytics", "image-prompts"];

const STATUS_BADGE: Record<ChangeStatus, { label: string; variant: "success" | "destructive" | "warning" | "default" }> = {
  added: { label: "New", variant: "success" },
  removed: { label: "Removed", variant: "destructive" },
  changed: { label: "Changed", variant: "warning" },
  unchanged: { label: "Unchanged", variant: "default" },
};

function StepTitle({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <CardTitle className="flex items-center gap-2.5">
      <span className="tabular flex size-6 items-center justify-center rounded-full bg-primary-soft text-xs font-bold text-primary">{n}</span>
      {children}
    </CardTitle>
  );
}

// --------------------------------------------------------------------------- step 1

function AskStep() {
  const { profile } = useProfile();
  const status = useQuery({ queryKey: ["assistant-status"], queryFn: api.assistantStatus });
  const [request, setRequest] = React.useState("");
  const [prompt, setPrompt] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);

  const create = useMutation({
    mutationFn: () => api.assistantPrompt(request),
    onSuccess: (data) => setPrompt(data.prompt),
  });
  const email = useMutation({
    mutationFn: () => api.emailAssistantPrompt(request),
    onSuccess: (data) => toast.success(`Prompt sent to ${data.sent_to}`),
  });

  const copy = async () => {
    if (!prompt) return;
    if (await copyText(prompt)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } else {
      toast.error("Couldn't copy. Use Download or Email instead.");
    }
  };

  const emailReady = status.data?.email_enabled && status.data.email;

  return (
    <Card>
      <CardHeader>
        <StepTitle n={1}>Describe what you want changed</StepTitle>
        <CardDescription>
          Plain words are fine. Ask for changes to the plan you have, or for a whole program that changes from week to week (say, 6 weeks). The prompt
          includes {profile.name}'s current plan, recent weights, your equipment and every exercise in the library.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Textarea
          rows={4}
          value={request}
          onChange={(e) => {
            setRequest(e.target.value);
            setPrompt(null);
          }}
          placeholder="e.g. I want to work on my glutes more and I only have 40 minutes on weekdays. Or: build me a 6-week program that gets harder each week."
          aria-label="What do you want changed?"
        />
        <div className="flex flex-wrap gap-1.5">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              onClick={() => {
                setRequest((r) => (r.trim() ? `${r.trim()}\n${example}` : example));
                setPrompt(null);
              }}
              className="rounded-full border border-border px-3 py-1 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              {example}
            </button>
          ))}
        </div>
        {!prompt ? (
          <Button className="w-full sm:w-auto" disabled={request.trim().length < 3 || create.isPending} onClick={() => create.mutate()}>
            <Sparkles /> {create.isPending ? "Writing prompt…" : "Create prompt"}
          </Button>
        ) : (
          <div className="space-y-3 rounded-2xl border border-primary/30 bg-primary-soft/40 p-4">
            <div className="flex items-center gap-2 font-semibold">
              <Check className="size-5 text-primary" /> Prompt ready
              <span className="text-sm font-normal text-muted-foreground">· {Math.round(prompt.length / 1000)}k characters</span>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <Button onClick={() => void copy()}>
                {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy prompt"}
              </Button>
              <Button variant="secondary" disabled={!emailReady || email.isPending} onClick={() => email.mutate()}>
                <Mail /> {email.isPending ? "Sending…" : "Email it to me"}
              </Button>
              <Button variant="secondary" onClick={() => downloadText("workout-pal-prompt.txt", prompt)}>
                <Download /> Download
              </Button>
            </div>
            {status.data && !status.data.email_enabled && (
              <p className="text-xs text-subtle">Email isn't set up on the server yet (see the README).</p>
            )}
            {status.data?.email_enabled && !status.data.email && (
              <p className="text-xs text-subtle">
                <Link to="/settings" className="underline">
                  Add {profile.name}'s email in Settings
                </Link>{" "}
                to send it to yourself.
              </p>
            )}
            <p className="text-sm text-muted-foreground">
              Paste it into ChatGPT, Claude or Gemini and answer any questions it asks. When it replies with a JSON block, bring the whole reply back to step 2.
            </p>
            <details className="text-sm">
              <summary className="cursor-pointer text-muted-foreground">Show the prompt</summary>
              <Textarea readOnly value={prompt} rows={10} className="mt-2 font-mono text-xs" aria-label="Prompt" />
            </details>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------- step 2

function fixRequest(errors: string[]): string {
  return `Workout Pal couldn't import that plan:\n${errors.map((e) => `- ${e}`).join("\n")}\n\nPlease fix these and send the complete corrected plan as one JSON block.`;
}

function WorkoutDiff({ workout }: { workout: PlanDiffWorkout }) {
  const badge = STATUS_BADGE[workout.status];
  const day = workout.status === "removed" ? workout.previous_day : workout.day;
  return (
    <div className="rounded-2xl border border-border p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className={cn("font-semibold", workout.status === "removed" && "line-through opacity-60")}>{workout.name}</div>
          <div className="text-sm text-muted-foreground">
            {day ?? "Not scheduled"}
            {workout.weeks && ` · ${workout.weeks_text}`}
          </div>
        </div>
        <Badge variant={badge.variant}>{badge.label}</Badge>
      </div>
      {workout.notes.length > 0 && <p className="mt-2 text-sm text-warning">{workout.notes.join(" · ")}</p>}
      {workout.status !== "removed" && (
        <ul className="mt-3 space-y-1.5 text-sm">
          {workout.exercises.map((e, i) => (
            <li key={`${e.exercise_id}-${i}`} className="flex gap-2">
              <span
                className={cn(
                  "w-4 shrink-0 text-center font-bold",
                  e.status === "added" && "text-success",
                  e.status === "removed" && "text-destructive",
                  e.status === "changed" && "text-warning",
                  e.status === "unchanged" && "text-subtle",
                )}
                aria-label={e.status}
              >
                {{ added: "+", removed: "−", changed: "~", unchanged: "·" }[e.status]}
              </span>
              <div className="min-w-0">
                <span className={cn(e.status === "removed" && "line-through opacity-60", e.status === "unchanged" && "text-muted-foreground")}>
                  {e.exercise_name}
                </span>
                <span className="text-subtle">
                  {" "}
                  · {e.sets} × {e.reps_or_duration}
                  {e.weight ? ` · ${e.weight} lb` : ""}
                </span>
                {e.changes.length > 0 && <div className="text-xs text-warning">{e.changes.join(", ")}</div>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Whether applying `preview` would change anything at all. */
function hasChanges(preview: PlanPreview): boolean {
  return preview.plan_weeks !== preview.previous_plan_weeks || preview.workouts.some((w) => w.status !== "unchanged");
}

function PreviewResult({ preview }: { preview: PlanPreview }) {
  const [copied, setCopied] = React.useState(false);
  const changed = preview.workouts.filter((w) => w.status !== "unchanged");
  const unchanged = preview.workouts.length - changed.length;
  const lengthChanged = preview.plan_weeks !== null && preview.plan_weeks !== preview.previous_plan_weeks;

  return (
    <div className="space-y-3">
      {preview.errors.length > 0 && (
        <div className="rounded-2xl border border-destructive/40 bg-destructive-soft p-4">
          <div className="font-semibold text-destructive">This answer can't be applied yet</div>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {preview.errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
          <Button
            size="sm"
            variant="secondary"
            className="mt-3"
            onClick={async () => {
              if (await copyText(fixRequest(preview.errors))) {
                setCopied(true);
                setTimeout(() => setCopied(false), 2500);
              }
            }}
          >
            {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy a message asking the AI to fix it"}
          </Button>
        </div>
      )}
      {preview.warnings.length > 0 && (
        <div className="rounded-2xl border border-warning/30 bg-warning-soft p-4">
          <div className="flex items-center gap-2 font-semibold text-warning">
            <AlertTriangle className="size-4" /> Worth a look
          </div>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {preview.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}
      {preview.ok && (
        <>
          {preview.summary && <blockquote className="border-l-2 border-primary pl-3 text-sm text-muted-foreground">{preview.summary}</blockquote>}
          {lengthChanged && (
            <p className="text-sm">
              <span className="font-semibold">{planLengthText(preview.plan_weeks!)}</span>
              <span className="text-muted-foreground"> (was: {planLengthText(preview.previous_plan_weeks).toLowerCase()})</span>
              {preview.plan_weeks! > 1 && <span className="text-muted-foreground">. After week {preview.plan_weeks} it starts again at week 1.</span>}
            </p>
          )}
          {changed.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {lengthChanged ? "The workouts themselves are unchanged." : "This plan is the same as the current one."}
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {changed.map((w) => (
                <WorkoutDiff key={w.name} workout={w} />
              ))}
            </div>
          )}
          {unchanged > 0 && changed.length > 0 && (
            <p className="text-sm text-subtle">
              {unchanged} other workout{unchanged === 1 ? "" : "s"} unchanged.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function ApplyStep() {
  const { profile } = useProfile();
  const [text, setText] = React.useState("");
  // The preview always belongs to `checked.text`: applying sends exactly the text that was previewed.
  const [checked, setChecked] = React.useState<{ text: string; preview: PlanPreview } | null>(null);
  const preview = checked?.preview ?? null;
  const [restart, setRestart] = React.useState(false);
  const fileInput = React.useRef<HTMLInputElement>(null);
  const latestText = React.useRef(text);
  latestText.current = text;
  // At the weekend, week 1 starts next Monday (the server does the same).
  const weekend = [0, 6].includes(new Date().getDay());
  const restartLabel = weekend ? "Start at week 1 on Monday" : "Start at week 1 this week";

  const check = useMutation({
    mutationFn: (document: string) => api.previewPlan(document),
    onSuccess: (p, document) => {
      if (document !== latestText.current) return; // edited while checking: that check is stale
      setChecked({ text: document, preview: p });
      // A new multi-week program usually starts at week 1; edits to the current one don't.
      setRestart((p.plan_weeks ?? 1) > 1 && p.plan_weeks !== p.previous_plan_weeks);
    },
  });
  const apply = useMutation({
    mutationFn: (c: { text: string; preview: PlanPreview }) => api.applyPlan(c.text, restart && (c.preview.plan_weeks ?? 1) > 1),
    onSuccess: () => {
      toast.success(`${profile.name}'s plan was updated`);
      setText("");
      setChecked(null);
      for (const key of REFRESH_AFTER_PLAN_CHANGE) void queryClient.invalidateQueries({ queryKey: [key] });
    },
  });

  const load = (value: string) => {
    setText(value);
    setChecked(null);
  };

  return (
    <Card>
      <CardHeader>
        <StepTitle n={2}>Paste the AI's answer</StepTitle>
        <CardDescription>Paste the whole reply; the app finds the plan in it. You'll see every change before anything is saved.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Textarea
          rows={6}
          value={text}
          onChange={(e) => load(e.target.value)}
          placeholder="Paste the AI's reply here…"
          className="font-mono text-sm"
          aria-label="The AI's answer"
        />
        <div className="flex flex-wrap gap-2">
          <Button disabled={!text.trim() || check.isPending} onClick={() => check.mutate(text)}>
            {check.isPending ? "Checking…" : "Check answer"}
          </Button>
          <Button variant="secondary" onClick={() => fileInput.current?.click()}>
            <FileUp /> Upload file
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept=".json,.txt,application/json,text/plain"
            className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              const content = await file.text();
              load(content);
              check.mutate(content);
            }}
          />
        </div>
        {preview && <PreviewResult preview={preview} />}
        {preview?.ok && hasChanges(preview) && (
          <>
            {(preview.plan_weeks ?? 1) > 1 && (
              <label className="flex items-center justify-between gap-3 rounded-xl border border-border px-4 py-3">
                <div>
                  <div className="font-medium">{restartLabel}</div>
                  <div className="text-sm text-muted-foreground">Off: stay in the plan week you're in now. Either way, your ramp-in isn't restarted.</div>
                </div>
                <Switch checked={restart} onCheckedChange={setRestart} aria-label={restartLabel} />
              </label>
            )}
            <Button size="lg" className="w-full" disabled={apply.isPending || !checked} onClick={() => checked && apply.mutate(checked)}>
              <Check /> {apply.isPending ? "Applying…" : `Apply to ${profile.name}'s plan`}
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------- history

function RevisionRow({ revision }: { revision: PlanRevision }) {
  const undo = useMutation({
    mutationFn: () => api.undoPlanRevision(revision.id),
    onSuccess: () => {
      toast.success("Change undone");
      for (const key of REFRESH_AFTER_PLAN_CHANGE) void queryClient.invalidateQueries({ queryKey: [key] });
    },
  });
  return (
    <li className="flex items-start gap-3 py-3">
      <div className="min-w-0 flex-1">
        <div className="text-sm">{revision.summary ?? (revision.source === "undo" ? "Undid a change" : "Plan updated")}</div>
        <div className="text-xs text-subtle">
          {new Date(revision.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
          {revision.undone_at && " · undone"}
        </div>
      </div>
      {revision.can_undo && (
        <Button size="sm" variant="secondary" disabled={undo.isPending} onClick={() => undo.mutate()}>
          <Undo2 /> Undo
        </Button>
      )}
    </li>
  );
}

export default function PlanAssistantPage() {
  const { profile } = useProfile();
  const revisions = useQuery({ queryKey: ["plan-revisions"], queryFn: api.planRevisions });

  return (
    <div className="space-y-4">
      <header className="pb-1 pt-4 lg:pt-10">
        <Button asChild variant="ghost" size="sm" className="-ml-3 text-muted-foreground">
          <Link to="/schedule">
            <ChevronLeft /> Plan
          </Link>
        </Button>
        <p className="mt-1 text-sm font-medium text-muted-foreground">{profile.name}'s plan</p>
        <h1 className="text-[28px] font-bold leading-tight tracking-tight lg:text-3xl">Change with AI</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Describe what you want, give the prompt to any AI chat, then paste its answer back here.
        </p>
      </header>

      <AskStep />
      <ApplyStep />

      {!!revisions.data?.length && (
        <Card>
          <CardHeader>
            <CardTitle>Recent changes</CardTitle>
            <CardDescription>The latest change can be undone. Past workouts are never affected.</CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            <ul className="divide-y divide-border">
              {revisions.data.map((r) => (
                <RevisionRow key={r.id} revision={r} />
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
