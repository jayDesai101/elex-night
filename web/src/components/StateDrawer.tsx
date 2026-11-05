import React from "react";
import { useAllRaces } from "../api/client";
import type { Race } from "../api/types";
import { getPartyColor } from "../lib/scales";
import { leaderOf } from "../lib/useCountUp";

const ORDER: Record<string, number> = { senate: 0, governor: 1, house: 2 };

/** Slide-in panel listing every race in the zoomed state. */
export const StateDrawer: React.FC<{
  po: string | null;
  name: string;
  onClose: () => void;
  expanded?: boolean;
  onPointerEnter?: () => void;
}> = ({ po, name, onClose, expanded = false, onPointerEnter }) => {
  const q = useAllRaces(po !== null);
  const races: Race[] = (q.data ?? [])
    .filter((r) => r.province === po)
    .sort((a, b) => ORDER[a.office] - ORDER[b.office] || (a.district ?? "").localeCompare(b.district ?? ""));
  return (
    <aside
      onPointerEnter={onPointerEnter}
      className={`z-30 flex flex-col rounded-xl border border-slate-700 bg-slate-900/95 shadow-2xl backdrop-blur sm:absolute sm:bottom-2 sm:right-16 sm:top-14 sm:mt-0 sm:max-h-none sm:w-80 ${
        // phones: below the map on the page; over the bottom of the full-screen map
        expanded
          ? "absolute inset-x-2 bottom-2 max-h-[45%] sm:inset-x-auto"
          : "relative mt-2 max-h-80 w-full"
      }`}
    >
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-2">
        <div>
          <div className="text-sm font-bold text-slate-100">{name}</div>
          <div className="text-[11px] text-slate-400">{races.length} races on the ballot</div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close state panel" className="flex h-10 w-10 items-center justify-center rounded text-slate-400 hover:text-white">
          ✕
        </button>
      </div>
      <ul className="flex-1 space-y-1 overflow-y-auto p-2">
        {q.isLoading && <li className="p-2 text-xs text-slate-400">Loading races…</li>}
        {races.map((r) => {
          const lead = leaderOf(r.candidates);
          return (
            <li key={r.race_id} className="rounded-lg bg-slate-950/50 px-2.5 py-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-slate-200">
                  {r.office === "house" ? `House ${r.district ?? ""}` : r.office === "senate" ? "Senate" : "Governor"}
                </span>
                <span className="font-mono text-slate-400">{(r.pct_reporting ?? 0).toFixed(0)}% in</span>
              </div>
              <div className="mt-0.5 flex items-center gap-1.5 text-slate-300">
                {lead ? (
                  <>
                    <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: getPartyColor(lead.party_code) }} />
                    <span className="truncate">{lead.name}</span>
                    <span className="ml-auto font-mono">
                      {(r.candidates.find((c) => c.name === lead.name)?.pct ?? 0).toFixed(1)}%
                    </span>
                  </>
                ) : (
                  <span className="text-slate-500">No votes yet</span>
                )}
                {r.winner_party && <span className="text-emerald-400">✓</span>}
              </div>
            </li>
          );
        })}
      </ul>
    </aside>
  );
};
