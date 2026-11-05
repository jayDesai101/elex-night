import React from "react";
import type { ReplayClock } from "../lib/replay";

const etTime = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "numeric",
  minute: "2-digit",
});
const etDay = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  weekday: "short",
  month: "short",
  day: "numeric",
});

/** Live by default: a compact LIVE strip with "Watch the night". While replaying: the
 * replay clock, play/pause, a scrubber with its progress filled, and "Back to live". */
export const ReplayBar: React.FC<{ clock: ReplayClock }> = ({ clock }) => {
  const { index, i, live, playing, setI, toggle, watch, goLive } = clock;
  const n = index?.steps.length ?? 0;
  const canReplay = n > 1;

  if (live) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-emerald-500/30 bg-slate-900/90 px-4 py-2.5 shadow">
        <span className="live-ping h-2.5 w-2.5 shrink-0 rounded-full bg-emerald-400" />
        <div className="min-w-0 flex-1 leading-tight">
          <div className="text-xs font-semibold uppercase tracking-wider text-emerald-400">Live</div>
          <div className="truncate text-xs text-slate-400">Results update every 30 seconds</div>
        </div>
        {canReplay && (
          <button
            type="button"
            onClick={watch}
            className="lift flex shrink-0 items-center gap-2 rounded-lg bg-amber-400 px-3.5 py-2 text-sm font-semibold text-slate-950 hover:bg-amber-300"
          >
            <span aria-hidden>▶</span>
            <span>
              Watch the night<span className="hidden sm:inline"> unfold</span>
            </span>
          </button>
        )}
      </div>
    );
  }

  const at = index!.steps[Math.min(i, n - 1)];
  const pct = (100 * Math.min(i, n - 1)) / (n - 1);
  return (
    <div className="rounded-xl border border-amber-500/40 bg-slate-900/90 px-4 py-3 shadow">
      <div className="flex items-center gap-3">
        <span className="rounded bg-amber-400/15 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-amber-400">
          Replay
        </span>
        <div className="min-w-0 flex-1 leading-tight">
          <span className="font-mono text-lg font-semibold tabular-nums text-slate-100">
            {etTime.format(new Date(at))}
          </span>
          <span className="ml-1.5 text-xs text-slate-400">ET · {etDay.format(new Date(at))}</span>
        </div>
        <button
          type="button"
          onClick={goLive}
          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-emerald-500/40 px-3 py-1.5 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/10"
        >
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          Back to live
        </button>
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          type="button"
          onClick={toggle}
          aria-label={playing ? "Pause" : "Play"}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-400 text-sm text-slate-950 hover:bg-amber-300"
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <input
          type="range"
          min={0}
          max={n - 1}
          step={1}
          value={Math.min(i, n - 1)}
          onChange={(e) => setI(Number(e.target.value))}
          className="replay-range min-w-0 flex-1"
          style={{ "--pct": `${pct}%` } as React.CSSProperties}
          aria-label="Replay time"
        />
      </div>
    </div>
  );
};
