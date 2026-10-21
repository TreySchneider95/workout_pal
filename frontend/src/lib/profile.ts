/**
 * Who is using the app on this device. Every API request is sent for this
 * profile (X-Profile-Id); plans, history and settings are per person.
 */
const STORAGE_KEY = "workoutpal:profile:v1";

export const PROFILE_HEADER = "X-Profile-Id";

export function getProfileId(): number | null {
  try {
    const id = Number(localStorage.getItem(STORAGE_KEY));
    return Number.isInteger(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

export function storeProfileId(id: number | null) {
  try {
    if (id === null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, String(id));
  } catch {
    /* storage disabled: the choice lasts until the page is reloaded */
  }
}
