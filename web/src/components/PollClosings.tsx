import React, { useEffect, useMemo, useState } from "react";
import { useAllRaces } from "../api/client";
import { formatET } from "../lib/format";

function countdown(ms: number): string {
  const m = Math.round(ms / 60000);
  if (m < 60) return `in ${m} min`;
  return `in ${Math.floor(m / 60)}h ${m % 60}m`;
}

/** Closing times (ET) from each race's polls_close, with the states closing then. */
export const PollClosings: React.FC = () => {
  const q = useAllRaces(true);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);
  const groups = useMemo(() => {
    const by = new Map<string, Set<string>>();
    for (const r of q.data ?? []) {
      if (!r.polls_close || !r.province) continue;
      const set = by.get(r.polls_close) ?? new Set<string>();
      set.add(r.province);
      by.set(r.polls_close, set);
    }
    return [...by.entries()]
      .map(([t, s]) => ({ t, ms: Date.parse(t), states: [...s].sort() }))
      .sort((a, b) => a.ms - b.ms);
  }, [q.data]);
  const nextIdx = groups.findIndex((g) => g.ms > now);

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">Poll closings</h2>
        <span className="text-xs text-slate-400">Eastern Time</span>
      </div>
      {groups.length === 0 ? (
        <p className="text-sm text-slate-400">{q.isLoading ? "Loading…" : "No closing times yet"}</p>
      ) : (
        <ol className="max-h-80 space-y-2 overflow-y-auto pr-1">
          {groups.map((g, i) => {
            const closed = g.ms <= now;
            const next = i === nextIdx;
            return (
              <li
                key={g.t}
                className={`rounded-lg border px-3 py-2 ${
                  next ? "border-blue-500/60 bg-blue-500/10" : "border-slate-800 bg-slate-950/40"
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="font-mono font-semibold text-slate-100">{formatET(g.t)}</span>
                  <span className={closed ? "text-emerald-400" : next ? "font-semibold text-blue-400" : "text-slate-400"}>
                    {closed ? "✓ Closed" : countdown(g.ms - now)}
                  </span>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {g.states.map((s) => (
                    <span
                      key={s}
                      className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${
                        closed ? "bg-slate-800 text-slate-300" : "bg-slate-800/40 text-slate-400"
                      }`}
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
};
