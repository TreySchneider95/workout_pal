/**
 * Autosave queue for set edits.
 *
 * Every change to a set is merged into a pending patch, written to localStorage
 * immediately, and sent to the server shortly after. If the network drops (phone
 * Wi-Fi in a garage...) the patches stay queued and are retried; if the page is
 * refreshed they are reloaded from localStorage and re-applied on top of the
 * server data, so nothing typed is lost.
 */
import { ApiError } from "./api";
import { getProfileId } from "./profile";
import type { ExerciseSet, SetPatch } from "./types";

export type SaveStatus = "idle" | "pending" | "saving" | "offline" | "error";

export type Transport = (
  sessionId: number,
  setId: number,
  patch: SetPatch,
  keepalive: boolean,
  profileId: number | null,
) => Promise<ExerciseSet>;

interface Entry {
  sessionId: number;
  setId: number;
  patch: SetPatch;
  version: number;
  /** Whose workout this is, so a save still lands after switching profiles. */
  profileId?: number | null;
}

const STORAGE_KEY = "workoutpal:pending-sets:v1";
const DEBOUNCE_MS = 350;
const MAX_BACKOFF_MS = 15_000;

function read(storage: Storage | undefined): Entry[] {
  if (!storage) return [];
  try {
    const raw = storage.getItem(STORAGE_KEY);
    const parsed = raw ? (JSON.parse(raw) as Entry[]) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export class SaveQueue {
  private entries = new Map<string, Entry>();
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private flushing: Promise<void> | null = null;
  private backoff = 0;
  private version = 0;
  status: SaveStatus = "idle";
  lastError: string | null = null;

  constructor(
    private transport: Transport,
    private storage: Storage | undefined = typeof localStorage !== "undefined" ? localStorage : undefined,
    private onSaved?: (sessionId: number, set: ExerciseSet) => void,
    private onRejected?: (sessionId: number, setId: number, message: string) => void,
  ) {
    for (const entry of read(storage)) this.entries.set(this.key(entry.sessionId, entry.setId), entry);
    if (this.entries.size) this.setStatus("pending");
  }

  setCallbacks(onSaved?: SaveQueue["onSaved"], onRejected?: SaveQueue["onRejected"]) {
    this.onSaved = onSaved;
    this.onRejected = onRejected;
  }

  private key(sessionId: number, setId: number) {
    return `${sessionId}:${setId}`;
  }

  private persist() {
    try {
      this.storage?.setItem(STORAGE_KEY, JSON.stringify([...this.entries.values()]));
    } catch {
      /* storage full or disabled: the in-memory queue still works */
    }
  }

  private setStatus(status: SaveStatus) {
    this.status = status;
    this.emit();
  }

  private emit() {
    this.version += 1;
    this.listeners.forEach((l) => l());
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** Stable value for useSyncExternalStore. */
  getSnapshot = () => this.version;

  enqueue(sessionId: number, setId: number, patch: SetPatch) {
    const k = this.key(sessionId, setId);
    const existing = this.entries.get(k);
    this.entries.set(k, {
      sessionId,
      setId,
      patch: { ...existing?.patch, ...patch },
      version: (existing?.version ?? 0) + 1,
      profileId: existing?.profileId ?? getProfileId(),
    });
    this.persist();
    if (this.status !== "offline" && this.status !== "saving") this.setStatus("pending");
    else this.emit();
    this.schedule(DEBOUNCE_MS);
  }

  /** Pending (unsaved) patches for a session, keyed by set id. */
  pendingFor(sessionId: number): Map<number, SetPatch> {
    const result = new Map<number, SetPatch>();
    for (const e of this.entries.values()) if (e.sessionId === sessionId) result.set(e.setId, e.patch);
    return result;
  }

  hasPending(sessionId?: number) {
    if (sessionId === undefined) return this.entries.size > 0;
    return [...this.entries.values()].some((e) => e.sessionId === sessionId);
  }

  /** Forget a set (e.g. after it was deleted). */
  drop(sessionId: number, setId: number) {
    this.entries.delete(this.key(sessionId, setId));
    this.persist();
    this.emit();
  }

  dropSession(sessionId: number) {
    for (const [k, e] of this.entries) if (e.sessionId === sessionId) this.entries.delete(k);
    this.persist();
    this.emit();
  }

  private schedule(delay: number) {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.flush();
    }, delay);
  }

  /** Send everything now. Resolves when the queue is empty or the network failed. */
  flush(keepalive = false): Promise<void> {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.flushing) {
      return this.flushing.then(() => (this.entries.size ? this.flush(keepalive) : undefined));
    }
    this.flushing = this.run(keepalive).finally(() => {
      this.flushing = null;
    });
    return this.flushing;
  }

  private async run(keepalive: boolean) {
    if (!this.entries.size) {
      this.setStatus("idle");
      return;
    }
    this.setStatus("saving");
    for (const [k, entry] of [...this.entries]) {
      try {
        const saved = await this.transport(entry.sessionId, entry.setId, entry.patch, keepalive, entry.profileId ?? null);
        // Only clear if nothing changed while the request was in flight.
        if (this.entries.get(k)?.version === entry.version) this.entries.delete(k);
        this.persist();
        this.onSaved?.(entry.sessionId, saved);
      } catch (error) {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          // The server rejected this change (validation, deleted set...). Retrying won't help.
          this.entries.delete(k);
          this.persist();
          this.lastError = error.message;
          this.onRejected?.(entry.sessionId, entry.setId, error.message);
          continue;
        }
        this.backoff = Math.min(MAX_BACKOFF_MS, this.backoff ? this.backoff * 2 : 2000);
        this.setStatus("offline");
        this.schedule(this.backoff);
        return;
      }
    }
    this.backoff = 0;
    this.lastError = null;
    this.setStatus(this.entries.size ? "pending" : "idle");
    if (this.entries.size) this.schedule(DEBOUNCE_MS);
  }
}

export function applyPending<T extends ExerciseSet>(sets: T[], pending: Map<number, SetPatch>): T[] {
  if (!pending.size) return sets;
  return sets.map((s) => (pending.has(s.id) ? { ...s, ...pending.get(s.id) } : s));
}
