import { useEffect, useState } from "react";

/** One site, two modes. The archiver writes a replay step every 10 minutes under /replay
 * (served by the API). The page opens LIVE (polling the API); "Watch the night" plays the
 * steps from the first one and hands back to live at the last. Dragging back re-enters
 * replay.
 * VITE_REPLAY=0 at build time disables replay entirely (plain live site). */
export const REPLAY_ENABLED = import.meta.env.VITE_REPLAY !== "0";
export const REPLAY_BASE = `${import.meta.env.BASE_URL}replay`;

/** True while the page shows a replay step; false once it has handed over to live. */
export function inReplay(): boolean {
  return REPLAY_ENABLED && !live;
}

export interface ReplayIndex {
  steps: string[]; // ISO UTC times, ascending, one folder each (e.g. 20261104T011000Z)
  keys: string[]; // folder names matching steps
}

export interface ReplayClock {
  index: ReplayIndex | null;
  i: number; // current step
  live: boolean; // handed over to the live API
  playing: boolean;
  setI: (i: number) => void;
  toggle: () => void;
  watch: () => void; // replay from the first step, playing
  goLive: () => void; // jump back to live
}

let indexPromise: Promise<ReplayIndex> | null = null;
export function loadIndex(fresh = false): Promise<ReplayIndex> {
  if (!indexPromise || fresh) {
    indexPromise = fetch(`${REPLAY_BASE}/index.json`, { cache: "no-store" }).then((r) => {
      if (!r.ok) throw new Error(`replay index: ${r.status}`);
      return r.json() as Promise<ReplayIndex>;
    });
  }
  return indexPromise;
}

/** Current replay step and live flag, shared through a tiny store so every query
 * re-keys on them. */
const listeners = new Set<() => void>();
let current = 0;
let live = true; // open on live; the replay starts only when asked
export function currentStep(): number {
  return current;
}
/** Query-key component: the step while replaying, "live" once handed over. */
export function modeKey(): number | string {
  return inReplay() ? current : "live";
}
function setStep(i: number, total: number) {
  current = i;
  live = total === 0 || i >= total - 1; // the last step is "now" (no steps: stay live)
  listeners.forEach((l) => l());
}

const STEP_MS = 900; // one 10-minute step every 0.9 s when playing

const INDEX_REFRESH_MS = 60_000; // the archiver appends steps while the page is open

export function useReplayClock(): ReplayClock {
  const [index, setIndex] = useState<ReplayIndex | null>(null);
  const [i, setLocal] = useState(current);
  const [isLive, setLiveLocal] = useState(live);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!REPLAY_ENABLED) return;
    const load = () =>
      loadIndex(true)
        .then((idx) => {
          setIndex(idx);
          if (idx.keys.length === 0) setStep(0, 0);
          // a page that has handed over to live stays on the newest step as steps arrive
          else if (live) setStep(idx.keys.length - 1, idx.keys.length);
        })
        .catch(() => setIndex({ steps: [], keys: [] }));
    load();
    const t = setInterval(load, INDEX_REFRESH_MS);
    const l = () => {
      setLocal(current);
      setLiveLocal(live);
    };
    listeners.add(l);
    return () => {
      clearInterval(t);
      listeners.delete(l);
    };
  }, []);
  useEffect(() => {
    if (!playing || !index) return;
    const n = index.keys.length;
    const t = setInterval(() => {
      if (current >= n - 1) setPlaying(false);
      else setStep(current + 1, n);
    }, STEP_MS);
    return () => clearInterval(t);
  }, [playing, index]);
  const n = index?.keys.length ?? 0;
  return {
    index,
    i,
    live: isLive,
    playing,
    setI: (k) => {
      setPlaying(false);
      setStep(k, n);
    },
    toggle: () => {
      if (n && current >= n - 1) setStep(0, n);
      setPlaying((p) => !p);
    },
    watch: () => {
      if (n < 2) return;
      setStep(0, n);
      setPlaying(true);
    },
    goLive: () => {
      setPlaying(false);
      if (n) setStep(n - 1, n);
    },
  };
}

/** Map an API path to the static file for the current step. */
export function replayPath(apiPath: string, key: string): string {
  const [path, qs] = apiPath.split("?");
  const name = path.replace(/^\/api\//, "").replace(/\//g, "_");
  const params = new URLSearchParams(qs ?? "");
  const suffix = [...params.entries()]
    .sort()
    .map(([k, v]) => `${k}-${v}`)
    .join("_");
  return `${REPLAY_BASE}/${key}/${name}${suffix ? `__${suffix}` : ""}.json`;
}
