import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { LOAD_LABEL, TRACKING_LABEL } from "@/lib/format";
import type { Exercise, ExerciseInput, LoadType, TrackingType } from "@/lib/types";

/** Create / edit an exercise's library details. */
export function ExerciseForm({
  initial,
  submitLabel,
  onSubmit,
}: {
  initial?: Exercise;
  submitLabel: string;
  onSubmit: (body: ExerciseInput) => Promise<unknown>;
}) {
  const equipment = useQuery({ queryKey: ["equipment"], queryFn: api.equipment });
  const muscles = useQuery({ queryKey: ["muscle-groups"], queryFn: api.muscleGroups });
  const [form, setForm] = React.useState<ExerciseInput>(() => ({
    name: initial?.name ?? "",
    primary_muscle_group: initial?.primary_muscle_group ?? "",
    secondary_muscles: initial?.secondary_muscles ?? [],
    equipment_id: initial?.equipment_id ?? null,
    equipment_detail: initial?.equipment_detail ?? "",
    attachment: initial?.attachment ?? "",
    tracking_type: initial?.tracking_type ?? "strength",
    load_type: initial?.load_type ?? "per_dumbbell",
    pulley_ratio: initial?.pulley_ratio ?? "",
    unilateral: initial?.unilateral ?? false,
    starting_weight: initial?.starting_weight ?? null,
    notes: initial?.notes ?? "",
  }));
  const [saving, setSaving] = React.useState(false);
  const set = (patch: ExerciseInput) => setForm((f) => ({ ...f, ...patch }));
  const ratioValid = !form.pulley_ratio || /^\d+:\d+$/.test(form.pulley_ratio);

  return (
    <form
      className="space-y-3"
      onSubmit={async (e) => {
        e.preventDefault();
        setSaving(true);
        try {
          await onSubmit({
            ...form,
            name: form.name?.trim(),
            primary_muscle_group: form.primary_muscle_group || null,
            equipment_detail: form.equipment_detail || null,
            attachment: form.attachment || null,
            pulley_ratio: form.pulley_ratio || null,
            notes: form.notes || null,
          });
        } finally {
          setSaving(false);
        }
      }}
    >
      <Field label="Name">
        <Input value={form.name} onChange={(e) => set({ name: e.target.value })} required />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Primary muscle group">
          <Input list="muscle-groups" value={form.primary_muscle_group ?? ""} onChange={(e) => set({ primary_muscle_group: e.target.value })} />
          <datalist id="muscle-groups">
            {muscles.data?.map((m) => <option key={m} value={m} />)}
          </datalist>
        </Field>
        <Field label="Secondary muscles" hint="Comma separated">
          <Input
            value={(form.secondary_muscles ?? []).join(", ")}
            onChange={(e) => set({ secondary_muscles: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })}
          />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Equipment (weight steps)">
          <Select value={form.equipment_id ?? ""} onChange={(e) => set({ equipment_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">None</option>
            {equipment.data?.map((eq) => (
              <option key={eq.id} value={eq.id}>
                {eq.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Equipment needed">
          <Input value={form.equipment_detail ?? ""} onChange={(e) => set({ equipment_detail: e.target.value })} placeholder="e.g. Dumbbells + bench" />
        </Field>
      </div>
      <Field label="Attachment">
        <Input value={form.attachment ?? ""} onChange={(e) => set({ attachment: e.target.value })} placeholder="e.g. Triceps rope" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Tracking">
          <Select value={form.tracking_type} onChange={(e) => set({ tracking_type: e.target.value as TrackingType })}>
            {Object.entries(TRACKING_LABEL).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Weight convention">
          <Select value={form.load_type} onChange={(e) => set({ load_type: e.target.value as LoadType })}>
            {Object.entries(LOAD_LABEL).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Starting weight (lb)">
          <Input
            type="number"
            inputMode="decimal"
            min={0}
            step="any"
            value={form.starting_weight ?? ""}
            onChange={(e) => set({ starting_weight: e.target.value === "" ? null : Number(e.target.value) })}
          />
        </Field>
        <Field label="Pulley ratio" hint={ratioValid ? "Cable only, e.g. 2:1" : "Use the form 2:1"}>
          <Input value={form.pulley_ratio ?? ""} onChange={(e) => set({ pulley_ratio: e.target.value })} placeholder="1:1" />
        </Field>
      </div>
      <div className="flex items-center justify-between rounded-xl border border-border px-4 py-3">
        <div>
          <div className="font-medium">Track left & right separately</div>
          <div className="text-sm text-muted-foreground">Each set gets a left and a right row</div>
        </div>
        <Switch checked={!!form.unilateral} onCheckedChange={(v) => set({ unilateral: v })} />
      </div>
      <Field label="Notes / instructions">
        <Textarea value={form.notes ?? ""} onChange={(e) => set({ notes: e.target.value })} />
      </Field>
      <Button type="submit" className="w-full" disabled={saving || !form.name?.trim() || !ratioValid}>
        {submitLabel}
      </Button>
    </form>
  );
}
