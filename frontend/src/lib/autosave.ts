import { api } from "./api";
import { PROFILE_HEADER } from "./profile";
import { SaveQueue } from "./saveQueue";

export const saveQueue = new SaveQueue((sessionId, setId, patch, keepalive, profileId) =>
  api.updateSet(sessionId, setId, patch, {
    keepalive,
    headers: profileId !== null ? { [PROFILE_HEADER]: String(profileId) } : undefined,
  }),
);

if (typeof window !== "undefined") {
  // Push pending changes when the phone is locked / app backgrounded, and when back online.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden" && saveQueue.hasPending()) void saveQueue.flush(true);
  });
  window.addEventListener("online", () => void saveQueue.flush());
  // Pending edits survive a refresh in localStorage, so no "leave page?" prompt is needed.
  window.addEventListener("pagehide", () => {
    if (saveQueue.hasPending()) void saveQueue.flush(true);
  });
  if (saveQueue.hasPending()) void saveQueue.flush();
}
