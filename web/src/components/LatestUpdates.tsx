import React, { useMemo } from "react";
import { useAllRaces } from "../api/client";
import { fullRaceLabel } from "../lib/format";
import { getPartyColor } from "../lib/scales";
import { leaderOf } from "../lib/useCountUp";

function ago(iso: string, now: number): string {
  const m = Math.max(0, Math.round((now - Date.parse(iso)) / 60000));
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  return `${Math.floor(m / 60)}h ago`;
}

/** Races whose counts changed most recently (civicAPI last_updated), with votes. */
export const LatestUpdates: React.FC<{ onSelectRace?: (id: number) => void }> = ({ onSelectRace }) => {
  const q = useAllRaces(true);
  const now = Date.now();
  const rows = useMemo(
    () =>
      (q.data ?? [])
        .filter((r) => r.last_updated && r.candidates.some((c) => c.votes > 0))
        .sort((a, b) => Date.parse(b.last_updated as string) - Date.parse(a.last_updated as string))
        .slice(0, 8),
    [q.data]
  );
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">Latest updates</h2>
        <span className="flex items-center gap-1.5 text-xs text-slate-400">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" /> live
        </span>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-slate-400">New counts appear here as they come in</p>
      ) : (
        <ul className="space-y-1.5">
          {rows.map((r) => {
            const lead = leaderOf(r.candidates);
            const pct = lead ? r.candidates.find((c) => c.name === lead.name)?.pct ?? 0 : 0;
            return (
              <li key={r.race_id}>
                <button
                  type="button"
                  onClick={() => onSelectRace?.(r.race_id)}
                  className="w-full rounded-lg bg-slate-950/40 px-3 py-2 text-left text-xs hover:bg-slate-800/70"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-semibold text-slate-200">
                      {r.office === "house" && r.district ? `${r.district} House` : fullRaceLabel(r.label)}
                    </span>
                    <span className="shrink-0 text-slate-500">{ago(r.last_updated as string, now)}</span>
                  </div>
                  {lead && (
                    <div className="mt-0.5 flex items-center gap-1.5 text-slate-300">
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: getPartyColor(lead.party_code) }} />
                      <span className="truncate">{lead.name}</span>
                      <span className="ml-auto font-mono">
                        {pct.toFixed(1)}% · {(r.pct_reporting ?? 0).toFixed(0)}% in
                      </span>
                    </div>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
};
