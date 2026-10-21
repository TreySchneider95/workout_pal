import { QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { saveQueue } from "./autosave";
import type { WorkoutSession } from "./types";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: true },
    mutations: {
      onError: (error) => toast.error(error instanceof Error ? error.message : "Something went wrong"),
    },
  },
});

export const sessionKey = (id: number) => ["session", id] as const;

// Keep the cached session in sync with what the server confirmed.
saveQueue.setCallbacks(
  (sessionId, saved) => {
    queryClient.setQueryData<WorkoutSession>(sessionKey(sessionId), (old) =>
      old
        ? {
            ...old,
            exercises: old.exercises.map((e) => ({
              ...e,
              sets: e.sets.map((s) => (s.id === saved.id ? saved : s)),
            })),
          }
        : old,
    );
  },
  (sessionId, _setId, message) => {
    toast.error(`A change could not be saved: ${message}`);
    void queryClient.invalidateQueries({ queryKey: sessionKey(sessionId) });
  },
);
