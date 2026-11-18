import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, ChevronLeft, Copy, ImageUp, Images } from "lucide-react";
import * as React from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { EmptyState } from "@/components/AppShell";
import { ExerciseImage } from "@/components/ExerciseImage";
import { PastePicture } from "@/components/PastePicture";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { useProfile } from "@/hooks/profile";
import { api } from "@/lib/api";
import { copyText } from "@/lib/clipboard";
import { queryClient } from "@/lib/queryClient";
import type { ImagePromptItem } from "@/lib/types";

type Person = "man" | "woman";
const PERSON_KEY = "workout-pal:image-prompt-person";

function savedPerson(): Person {
  try {
    return localStorage.getItem(PERSON_KEY) === "woman" ? "woman" : "man";
  } catch {
    return "man";
  }
}

function PictureRow({ item }: { item: ImagePromptItem }) {
  const ex = item.exercise;
  const [copied, setCopied] = React.useState(false);
  const fileInput = React.useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (file: File) => api.uploadExerciseImage(ex.id, file),
    onSuccess: () => {
      toast.success(`Picture saved for ${ex.name}`);
      for (const key of ["image-prompts", "exercises", "exercise", "templates", "template", "dashboard"]) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });

  const copy = async () => {
    // The prompt is already loaded, so the copy happens inside the tap (needed on iPhone).
    if (await copyText(item.prompt)) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } else {
      toast.error("Couldn't copy. Open “Show the prompt” and copy it from there.");
    }
  };

  return (
    <Card className="p-4">
      <div className="flex gap-3">
        <ExerciseImage thumbUrl={ex.thumb_url} imageUrl={ex.image_url} alt={ex.name} zoomable={item.has_image} className="size-16 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <Link to={`/exercises/${ex.id}`} className="font-semibold leading-snug hover:underline">
              {ex.name}
            </Link>
            {item.has_image && (
              <Badge variant="success" className="shrink-0">
                <Check /> Has a picture
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">{[ex.primary_muscle_group, ex.equipment_name].filter(Boolean).join(" · ")}</p>
          <p className="text-xs text-subtle">In {item.workouts.join(", ")}</p>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <Button size="sm" className="col-span-full" onClick={() => void copy()}>
          {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy prompt"}
        </Button>
        <PastePicture
          size="sm"
          variant="secondary"
          name={ex.id.toLowerCase()}
          label={upload.isPending ? "Uploading…" : "Paste picture"}
          disabled={upload.isPending}
          onPicture={(file) => upload.mutate(file)}
        />
        <Button size="sm" variant="secondary" disabled={upload.isPending} onClick={() => fileInput.current?.click()}>
          <ImageUp /> Upload file
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (file) upload.mutate(file);
          }}
        />
      </div>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-muted-foreground">Show the prompt</summary>
        <Textarea readOnly value={item.prompt} rows={10} className="mt-2 font-mono text-xs" aria-label={`Picture prompt for ${ex.name}`} />
      </details>
    </Card>
  );
}

export default function ExercisePicturesPage() {
  const { profile } = useProfile();
  const [person, setPerson] = React.useState<Person>(savedPerson);
  const [showAll, setShowAll] = React.useState(false);
  const items = useQuery({ queryKey: ["image-prompts", person], queryFn: () => api.imagePrompts(person) });

  const all = items.data ?? [];
  const missing = all.filter((i) => !i.has_image);
  const shown = showAll ? all : missing;

  return (
    <div className="space-y-4">
      <header className="pb-1 pt-4 lg:pt-10">
        <Button asChild variant="ghost" size="sm" className="-ml-3 text-muted-foreground">
          <Link to="/schedule">
            <ChevronLeft /> Plan
          </Link>
        </Button>
        <p className="mt-1 text-sm font-medium text-muted-foreground">{profile.name}'s plan</p>
        <h1 className="text-[28px] font-bold leading-tight tracking-tight lg:text-3xl">Exercise pictures</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          Make a how-to picture for each exercise in your plan that doesn't have one, in the same style as the others. Copy a prompt into an AI that
          makes images (ChatGPT or Gemini, for example), then copy the picture it makes and paste it here (or save it and upload the file).{" "}
          <span className="font-medium text-foreground">One exercise per prompt</span>: most AIs only make a few pictures a day. Pictures are shared
          by everyone using the app.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Picture shows a</span>
          <Select
            className="w-auto"
            value={person}
            onChange={(e) => {
              const value = e.target.value as Person;
              setPerson(value);
              try {
                localStorage.setItem(PERSON_KEY, value);
              } catch {
                /* only a convenience */
              }
            }}
          >
            <option value="man">man</option>
            <option value="woman">woman</option>
          </Select>
        </label>
        {all.length > missing.length && (
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <Switch checked={showAll} onCheckedChange={setShowAll} aria-label="Also show exercises that have a picture" />
            Also show exercises that have a picture
          </label>
        )}
      </div>

      {items.isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40" />
          ))}
        </div>
      ) : items.isError ? (
        <EmptyState icon={Images} title="Couldn't load your plan's exercises">
          <p>Check the connection to the app and try again.</p>
          <Button className="mt-4" variant="secondary" onClick={() => void items.refetch()}>
            Try again
          </Button>
        </EmptyState>
      ) : !all.length ? (
        <EmptyState icon={Images} title="No plan yet">
          <p>Once your plan has workouts, the exercises in it show up here.</p>
        </EmptyState>
      ) : !shown.length ? (
        <EmptyState icon={Check} title="Every exercise in your plan has a picture">
          <p>Turn on “Also show exercises that have a picture” to redo one.</p>
        </EmptyState>
      ) : (
        <>
          {!showAll && (
            <p className="text-sm text-muted-foreground">
              {missing.length} of {all.length} exercises in your plan {missing.length === 1 ? "has" : "have"} no picture.
            </p>
          )}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {shown.map((item) => (
              <PictureRow key={item.exercise.id} item={item} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
