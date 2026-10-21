import * as React from "react";

interface TimerState {
  /** Epoch ms when the rest ends (running), or null when paused/idle. */
  endsAt: number | null;
  /** Remaining ms while paused. */
  pausedRemaining: number | null;
  total: number; // seconds
  label: string;
}

interface RestTimerApi {
  state: TimerState | null;
  remaining: number; // seconds
  running: boolean;
  finished: boolean;
  start: (seconds: number, label?: string) => void;
  pause: () => void;
  resume: () => void;
  add: (seconds: number) => void;
  stop: () => void;
}

const STORAGE_KEY = "workoutpal:rest-timer:v1";
const RestTimerContext = React.createContext<RestTimerApi | null>(null);

function load(): TimerState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as TimerState) : null;
  } catch {
    return null;
  }
}

function save(state: TimerState | null) {
  try {
    if (state) localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

/** Drop any running timer (e.g. when someone else takes over the device). */
export function resetRestTimer() {
  save(null);
}

function chime() {
  try {
    const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new AudioCtx();
    [0, 0.22].forEach((offset) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.0001, ctx.currentTime + offset);
      gain.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + offset + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + offset + 0.18);
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + offset);
      osc.stop(ctx.currentTime + offset + 0.2);
    });
    setTimeout(() => void ctx.close(), 800);
  } catch {
    /* audio unavailable */
  }
}

export function RestTimerProvider({ children, sound = true }: { children: React.ReactNode; sound?: boolean }) {
  const [state, setState] = React.useState<TimerState | null>(load);
  const [now, setNow] = React.useState(() => Date.now());
  const alerted = React.useRef(false);

  const update = React.useCallback((next: TimerState | null) => {
    alerted.current = false;
    save(next);
    setState(next);
    setNow(Date.now());
  }, []);

  const remainingMs = state
    ? state.endsAt !== null
      ? state.endsAt - now
      : (state.pausedRemaining ?? 0)
    : 0;
  const running = !!state && state.endsAt !== null && remainingMs > 0;
  const finished = !!state && state.endsAt !== null && remainingMs <= 0;

  React.useEffect(() => {
    if (!state || state.endsAt === null) return;
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, [state]);

  React.useEffect(() => {
    if (finished && !alerted.current) {
      alerted.current = true;
      navigator.vibrate?.([200, 100, 200]);
      if (sound) chime();
      // Auto-dismiss the "rest over" state after a few seconds.
      const id = window.setTimeout(() => update(null), 6000);
      return () => window.clearTimeout(id);
    }
  }, [finished, sound, update]);

  const api = React.useMemo<RestTimerApi>(
    () => ({
      state,
      remaining: Math.max(0, Math.ceil(remainingMs / 1000)),
      running,
      finished,
      start: (seconds, label = "Rest") => {
        if (seconds <= 0) return;
        update({ endsAt: Date.now() + seconds * 1000, pausedRemaining: null, total: seconds, label });
      },
      pause: () => {
        if (state?.endsAt) update({ ...state, endsAt: null, pausedRemaining: Math.max(0, state.endsAt - Date.now()) });
      },
      resume: () => {
        if (state && state.endsAt === null && state.pausedRemaining !== null)
          update({ ...state, endsAt: Date.now() + state.pausedRemaining, pausedRemaining: null });
      },
      add: (seconds) => {
        if (!state) return;
        if (state.endsAt !== null) {
          const base = Math.max(state.endsAt, Date.now());
          const endsAt = Math.max(Date.now() + 1000, base + seconds * 1000);
          update({ ...state, endsAt, total: Math.max(state.total, Math.ceil((endsAt - Date.now()) / 1000)) });
        } else if (state.pausedRemaining !== null) {
          const pausedRemaining = Math.max(1000, state.pausedRemaining + seconds * 1000);
          update({ ...state, pausedRemaining, total: Math.max(state.total, Math.ceil(pausedRemaining / 1000)) });
        }
      },
      stop: () => update(null),
    }),
    [state, remainingMs, running, finished, update],
  );

  return <RestTimerContext.Provider value={api}>{children}</RestTimerContext.Provider>;
}

export function useRestTimer(): RestTimerApi {
  const ctx = React.useContext(RestTimerContext);
  if (!ctx) throw new Error("useRestTimer must be used inside RestTimerProvider");
  return ctx;
}
