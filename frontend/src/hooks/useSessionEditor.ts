import { useMutation, useQuery } from "@tanstack/react-query";
import * as React from "react";

import { api } from "@/lib/api";
import { saveQueue } from "@/lib/autosave";
import { queryClient, sessionKey } from "@/lib/queryClient";
import { applyPending } from "@/lib/saveQueue";
import type { SessionExercise, SetPatch, WorkoutSession } from "@/lib/types";

export function useSaveStatus() {
  React.useSyncExternalStore(saveQueue.subscribe, saveQueue.getSnapshot);
  return { status: saveQueue.status, pending: saveQueue.hasPending() };
}

/**
 * Loads a session and overlays unsaved local edits. Set edits go through the
 * autosave queue; structural changes (add/remove sets...) flush it first.
 */
const cacheKey = (id: number) => `workoutpal:session-cache:${id}`;

/** Last copy of the session seen on this device, so a refresh works without a connection. */
function readCachedSession(id: number): WorkoutSession | undefined {
  try {
    const raw = localStorage.getItem(cacheKey(id));
    return raw ? (JSON.parse(raw) as WorkoutSession) : undefined;
  } catch {
    return undefined;
  }
}

export function forgetCachedSession(id: number) {
  try {
    localStorage.removeItem(cacheKey(id));
  } catch {
    /* ignore */
  }
}

export function useSessionEditor(sessionId: number) {
  const query = useQuery({
    queryKey: sessionKey(sessionId),
    queryFn: () => api.session(sessionId),
    // Show the device copy instantly; it is refetched right away (updatedAt 0 = stale).
    initialData: () => readCachedSession(sessionId),
    initialDataUpdatedAt: 0,
    // Pending local edits are overlaid, so refetching never loses them.
    refetchOnWindowFocus: true,
  });
  React.useSyncExternalStore(saveQueue.subscribe, saveQueue.getSnapshot);

  React.useEffect(() => {
    if (!query.data) return;
    try {
      if (query.data.status === "in_progress") localStorage.setItem(cacheKey(sessionId), JSON.stringify(query.data));
      else localStorage.removeItem(cacheKey(sessionId));
    } catch {
      /* storage full or disabled */
    }
  }, [query.data, sessionId]);

  const session: WorkoutSession | undefined = React.useMemo(() => {
    if (!query.data) return undefined;
    const pending = saveQueue.pendingFor(sessionId);
    if (!pending.size) return query.data;
    return {
      ...query.data,
      exercises: query.data.exercises.map((e) => ({ ...e, sets: applyPending(e.sets, pending) })),
    };
  }, [query.data, sessionId, saveQueue.getSnapshot()]);

  const refresh = React.useCallback(
    () => queryClient.invalidateQueries({ queryKey: sessionKey(sessionId) }),
    [sessionId],
  );

  const changeSet = React.useCallback(
    (setId: number, patch: SetPatch) => saveQueue.enqueue(sessionId, setId, patch),
    [sessionId],
  );

  const structural = useMutation({
    mutationFn: async (action: () => Promise<unknown>) => {
      await saveQueue.flush();
      return action();
    },
    onSettled: () => {
      void refresh();
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const run = (action: () => Promise<unknown>) => structural.mutateAsync(action);

  return {
    query,
    session,
    busy: structural.isPending,
    refresh,
    changeSet,
    addSet: (se: SessionExercise) => run(() => api.addSet(sessionId, se.id)),
    removeLastSet: (se: SessionExercise) => {
      const last = se.sets[se.sets.length - 1];
      if (!last) return Promise.resolve();
      return run(async () => {
        await api.deleteSet(sessionId, last.id);
        se.sets.filter((s) => s.set_number === last.set_number).forEach((s) => saveQueue.drop(sessionId, s.id));
      });
    },
    applyWeight: (se: SessionExercise, weight: number) => run(() => api.applyWeight(sessionId, se.id, weight)),
    toggleSkip: (se: SessionExercise) =>
      run(() => api.updateSessionExercise(sessionId, se.id, { status: se.status === "skipped" ? "active" : "skipped" })),
    saveNotes: (se: SessionExercise, notes: string) =>
      run(() => api.updateSessionExercise(sessionId, se.id, { notes: notes || null })),
    addExercise: (exerciseId: string) => run(() => api.addSessionExercise(sessionId, exerciseId)),
    removeExercise: (se: SessionExercise) => run(() => api.removeSessionExercise(sessionId, se.id)),
  };
}
