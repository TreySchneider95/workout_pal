import type {
  AnalyticsSummary,
  AppSettings,
  Dashboard,
  Equipment,
  Exercise,
  ExerciseInput,
  ExerciseProgress,
  ExerciseSet,
  AssistantStatus,
  HistoryPage,
  PlanPreview,
  PlanRevision,
  Profile,
  SessionExercise,
  SessionSummary,
  SetPatch,
  Template,
  TemplateExerciseInput,
  WorkoutSession,
} from "./types";
import { PROFILE_HEADER, getProfileId } from "./profile";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function messageFrom(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  if (Array.isArray(detail) && detail[0]?.msg) {
    const first = detail[0] as { msg: string; loc?: unknown[] };
    const field = first.loc?.[first.loc.length - 1];
    return field ? `${String(field)}: ${first.msg}` : first.msg;
  }
  return fallback;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  // Callers may pin a profile (queued saves keep the one they were made under).
  const profileId = getProfileId();
  if (!headers.has(PROFILE_HEADER) && profileId !== null) headers.set(PROFILE_HEADER, String(profileId));
  const response = await fetch(path, { ...init, headers });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = data?.detail;
    throw new ApiError(response.status, messageFrom(detail, `Request failed (${response.status})`), detail);
  }
  return data as T;
}

const json = (body: unknown) => JSON.stringify(body);

/** The device's local calendar date (the server may run in UTC). */
export function localDate(d: Date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export const api = {
  profiles: () => request<Profile[]>("/api/profiles"),
  updateProfile: (id: number, body: { email: string | null }) =>
    request<Profile>(`/api/profiles/${id}`, { method: "PATCH", body: json(body) }),

  assistantStatus: () => request<AssistantStatus>("/api/plan-assistant/status"),
  assistantPrompt: (text: string) =>
    request<{ prompt: string }>(`/api/plan-assistant/prompt?date=${localDate()}`, { method: "POST", body: json({ request: text }) }),
  emailAssistantPrompt: (text: string) =>
    request<{ sent_to: string }>(`/api/plan-assistant/email?date=${localDate()}`, { method: "POST", body: json({ request: text }) }),
  previewPlan: (document: string) =>
    request<PlanPreview>("/api/plan-assistant/preview", { method: "POST", body: json({ document }) }),
  applyPlan: (document: string) =>
    request<PlanRevision>("/api/plan-assistant/apply", { method: "POST", body: json({ document }) }),
  planRevisions: () => request<PlanRevision[]>("/api/plan-assistant/revisions"),
  undoPlanRevision: (id: number) => request<PlanRevision>(`/api/plan-assistant/revisions/${id}/undo`, { method: "POST" }),

  dashboard: () => request<Dashboard>(`/api/dashboard?date=${localDate()}`),

  settings: () => request<AppSettings>("/api/settings"),
  updateSettings: (body: Partial<AppSettings> & { clear_program_start_date?: boolean }) =>
    request<AppSettings>("/api/settings", { method: "PATCH", body: json(body) }),

  equipment: () => request<Equipment[]>("/api/equipment"),
  updateEquipment: (id: number, body: Partial<Equipment>) =>
    request<Equipment>(`/api/equipment/${id}`, { method: "PATCH", body: json(body) }),

  exercises: (params: { search?: string; muscle?: string; equipment_id?: number; include_disabled?: boolean } = {}) => {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "" && v !== null) q.set(k, String(v));
    });
    return request<Exercise[]>(`/api/exercises?${q}`);
  },
  muscleGroups: () => request<string[]>("/api/exercises/muscle-groups"),
  exercise: (id: string) => request<Exercise>(`/api/exercises/${id}`),
  createExercise: (body: ExerciseInput) => request<Exercise>("/api/exercises", { method: "POST", body: json(body) }),
  updateExercise: (id: string, body: ExerciseInput) =>
    request<Exercise>(`/api/exercises/${id}`, { method: "PATCH", body: json(body) }),
  uploadExerciseImage: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Exercise>(`/api/exercises/${id}/image`, { method: "POST", body: form });
  },
  exerciseProgress: (id: string) => request<ExerciseProgress>(`/api/exercises/${id}/progress`),

  templates: () => request<Template[]>(`/api/workout-templates?date=${localDate()}`),
  template: (id: number) => request<Template>(`/api/workout-templates/${id}?date=${localDate()}`),
  createTemplate: (body: { name: string; weekday?: number | null; copy_from_template_id?: number }) =>
    request<Template>("/api/workout-templates", { method: "POST", body: json(body) }),
  updateTemplate: (
    id: number,
    body: { name?: string; weekday?: number; unschedule?: boolean; notes?: string | null; estimated_duration_minutes?: number | null },
  ) => request<Template>(`/api/workout-templates/${id}`, { method: "PATCH", body: json(body) }),
  deleteTemplate: (id: number) => request<void>(`/api/workout-templates/${id}`, { method: "DELETE" }),
  addTemplateExercise: (id: number, body: TemplateExerciseInput & { exercise_id: string }) =>
    request<Template>(`/api/workout-templates/${id}/exercises`, { method: "POST", body: json(body) }),
  updateTemplateExercise: (id: number, teId: number, body: TemplateExerciseInput) =>
    request<Template>(`/api/workout-templates/${id}/exercises/${teId}`, { method: "PATCH", body: json(body) }),
  removeTemplateExercise: (id: number, teId: number) =>
    request<Template>(`/api/workout-templates/${id}/exercises/${teId}`, { method: "DELETE" }),
  reorderTemplate: (id: number, ids: number[]) =>
    request<Template>(`/api/workout-templates/${id}/reorder`, { method: "POST", body: json({ template_exercise_ids: ids }) }),

  activeSession: () => request<SessionSummary | null>("/api/workout-sessions/active"),
  session: (id: number) => request<WorkoutSession>(`/api/workout-sessions/${id}`),
  startSession: (templateId: number | null, name?: string) =>
    request<WorkoutSession>("/api/workout-sessions", {
      method: "POST",
      body: json({ workout_template_id: templateId, performed_on: localDate(), name }),
    }),
  updateSession: (
    id: number,
    body: { name?: string; notes?: string | null; performed_on?: string; started_at?: string; completed_at?: string | null },
  ) => request<WorkoutSession>(`/api/workout-sessions/${id}`, { method: "PATCH", body: json(body) }),
  completeSession: (id: number, notes?: string | null) =>
    request<WorkoutSession>(`/api/workout-sessions/${id}/complete`, { method: "POST", body: json({ notes }) }),
  resumeSession: (id: number) => request<WorkoutSession>(`/api/workout-sessions/${id}/resume`, { method: "POST" }),
  deleteSession: (id: number) => request<void>(`/api/workout-sessions/${id}`, { method: "DELETE" }),
  addSessionExercise: (id: number, exerciseId: string) =>
    request<SessionExercise>(`/api/workout-sessions/${id}/exercises`, { method: "POST", body: json({ exercise_id: exerciseId }) }),
  updateSessionExercise: (id: number, seId: number, body: { status?: "active" | "skipped"; notes?: string | null }) =>
    request<SessionExercise>(`/api/workout-sessions/${id}/exercises/${seId}`, { method: "PATCH", body: json(body) }),
  removeSessionExercise: (id: number, seId: number) =>
    request<void>(`/api/workout-sessions/${id}/exercises/${seId}`, { method: "DELETE" }),
  applyWeight: (id: number, seId: number, weight: number) =>
    request<SessionExercise>(`/api/workout-sessions/${id}/exercises/${seId}/apply-weight`, {
      method: "POST",
      body: json({ weight }),
    }),
  addSet: (id: number, seId: number) =>
    request<ExerciseSet[]>(`/api/workout-sessions/${id}/exercises/${seId}/sets`, { method: "POST" }),
  updateSet: (id: number, setId: number, patch: SetPatch, init: RequestInit = {}) =>
    request<ExerciseSet>(`/api/workout-sessions/${id}/sets/${setId}`, { method: "PATCH", body: json(patch), ...init }),
  deleteSet: (id: number, setId: number) => request<void>(`/api/workout-sessions/${id}/sets/${setId}`, { method: "DELETE" }),

  history: (offset = 0, limit = 20) => request<HistoryPage>(`/api/history?offset=${offset}&limit=${limit}`),
  analytics: () => request<AnalyticsSummary>(`/api/analytics/summary?date=${localDate()}`),
};
