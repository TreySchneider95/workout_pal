/**
 * Automatic sign-out for a shared device (the kitchen/garage touch screen):
 * after an hour without a touch or key press, go back to "Who's training?".
 *
 * The last activity time is kept in localStorage so it also applies after a
 * reload, a power cut or the screen sleeping (timers don't run while asleep).
 */
const STORAGE_KEY = "workoutpal:last-active:v1";

export const IDLE_SIGN_OUT_MS = 60 * 60 * 1000;

export function lastActive(): number | null {
  try {
    const t = Number(localStorage.getItem(STORAGE_KEY));
    return Number.isFinite(t) && t > 0 ? t : null;
  } catch {
    return null;
  }
}

export function markActive(now = Date.now()) {
  try {
    localStorage.setItem(STORAGE_KEY, String(now));
  } catch {
    /* storage disabled: the in-page timer still works */
  }
}

export function isIdle(now = Date.now(), limit = IDLE_SIGN_OUT_MS): boolean {
  const t = lastActive();
  return t !== null && now - t >= limit;
}
