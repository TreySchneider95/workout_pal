import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import { storeProfileId } from "@/lib/profile";
import { SaveQueue, applyPending, type Transport } from "@/lib/saveQueue";
import type { ExerciseSet } from "@/lib/types";

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
    clear: () => data.clear(),
    key: (i) => [...data.keys()][i] ?? null,
    get length() {
      return data.size;
    },
  };
}

const savedSet = (id: number, patch: object): ExerciseSet => ({
  id,
  set_number: 1,
  side: null,
  weight: 20,
  repetitions: 8,
  duration_seconds: null,
  distance: null,
  speed: null,
  completed: false,
  completed_at: null,
  ...patch,
});

describe("SaveQueue", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("merges edits to the same set and sends one request", async () => {
    const transport = vi.fn<Transport>(async (_s, id, patch) => savedSet(id, patch));
    const q = new SaveQueue(transport, memoryStorage());
    q.enqueue(1, 10, { weight: 25 });
    q.enqueue(1, 10, { repetitions: 9 });
    q.enqueue(1, 10, { completed: true });
    await vi.runAllTimersAsync();
    expect(transport).toHaveBeenCalledTimes(1);
    expect(transport.mock.calls[0][2]).toEqual({ weight: 25, repetitions: 9, completed: true });
    expect(q.hasPending()).toBe(false);
    expect(q.status).toBe("idle");
  });

  it("saves edits for the profile they were made under", async () => {
    const transport = vi.fn<Transport>(async (_s, id, patch) => savedSet(id, patch));
    const q = new SaveQueue(transport, memoryStorage());
    storeProfileId(1);
    q.enqueue(1, 10, { repetitions: 9 });
    storeProfileId(2); // someone else picks up the phone before it was sent
    q.enqueue(1, 10, { completed: true });
    await vi.runAllTimersAsync();
    expect(transport.mock.calls[0][4]).toBe(1);
    storeProfileId(null);
  });

  it("persists edits so they survive a page refresh", () => {
    const storage = memoryStorage();
    const first = new SaveQueue(vi.fn<Transport>(), storage);
    first.enqueue(1, 10, { repetitions: 7, completed: true });
    // Simulate reload before the debounce fired.
    const second = new SaveQueue(vi.fn<Transport>(), storage);
    expect(second.pendingFor(1).get(10)).toEqual({ repetitions: 7, completed: true });
  });

  it("keeps changes and retries when the network fails", async () => {
    let online = false;
    const transport = vi.fn<Transport>(async (_s, id, patch) => {
      if (!online) throw new TypeError("Failed to fetch");
      return savedSet(id, patch);
    });
    const storage = memoryStorage();
    const q = new SaveQueue(transport, storage);
    q.enqueue(1, 10, { completed: true });
    await vi.advanceTimersByTimeAsync(400);
    expect(q.status).toBe("offline");
    expect(q.hasPending(1)).toBe(true);
    expect(storage.getItem("workoutpal:pending-sets:v1")).toContain('"completed":true');

    online = true;
    await vi.advanceTimersByTimeAsync(2500);
    expect(q.hasPending()).toBe(false);
    expect(q.status).toBe("idle");
  });

  it("does not drop an edit made while a save is in flight", async () => {
    let release: () => void = () => {};
    const transport = vi.fn<Transport>(
      (_s, id, patch) => new Promise((resolve) => (release = () => resolve(savedSet(id, patch)))),
    );
    const q = new SaveQueue(transport, memoryStorage());
    q.enqueue(1, 10, { repetitions: 8 });
    await vi.advanceTimersByTimeAsync(400);
    q.enqueue(1, 10, { repetitions: 9 }); // typed while the first request is pending
    release();
    await vi.advanceTimersByTimeAsync(0);
    expect(q.pendingFor(1).get(10)).toEqual({ repetitions: 9 });
    await vi.advanceTimersByTimeAsync(400);
    release();
    await vi.runAllTimersAsync();
    expect(transport).toHaveBeenCalledTimes(2);
    expect(transport.mock.calls[1][2]).toEqual({ repetitions: 9 });
  });

  it("drops changes the server rejects and reports them", async () => {
    const onRejected = vi.fn();
    const transport = vi.fn<Transport>(async () => {
      throw new ApiError(422, "repetitions: too large");
    });
    const q = new SaveQueue(transport, memoryStorage(), undefined, onRejected);
    q.enqueue(1, 10, { repetitions: 9999 });
    await vi.runAllTimersAsync();
    expect(onRejected).toHaveBeenCalledWith(1, 10, "repetitions: too large");
    expect(q.hasPending()).toBe(false);
  });

  it("overlays pending edits on server data", () => {
    const sets = [savedSet(10, {}), savedSet(11, {})];
    const merged = applyPending(sets, new Map([[11, { repetitions: 12, completed: true }]]));
    expect(merged[0]).toBe(sets[0]);
    expect(merged[1]).toMatchObject({ repetitions: 12, completed: true, weight: 20 });
  });
});
