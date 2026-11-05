import React from "react";
import { fullRaceLabel } from "../lib/format";
import type { Race } from "../api/types";
import { getPartyColor } from "../lib/scales";
import { CandidateAvatar } from "./CandidateAvatar";
import { Num } from "./Num";
import { flashClass, useFlash } from "../lib/useFlash";

export interface RaceSpotlightProps {
  race: Race | null;
  isLoading: boolean;
}


/** The selected key race up close: photos, votes and vote share for every candidate. */
export const RaceSpotlight: React.FC<RaceSpotlightProps> = ({ race, isLoading }) => {
  if (isLoading) {
    return <div className="h-64 animate-pulse rounded-xl bg-slate-900/60" />;
  }
  if (!race) {
    return (
      <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5 text-sm text-slate-400">
        Select a key race to see its candidates.
      </section>
    );
  }
  const total = race.candidates.reduce((s, c) => s + c.votes, 0);
  const flash = useFlash(`${race.race_id}:${total}:${race.pct_reporting}`);
  const shown = race.candidates.slice(0, 4);
  return (
    <section className={`rounded-xl border border-slate-800 bg-slate-900/60 p-5 ${flashClass(flash)}`}>
      <header className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">{fullRaceLabel(race.label)}</h2>
          <p className="text-xs uppercase tracking-wide text-slate-400">
            {race.office} {race.district ? `· ${race.district}` : race.province ? `· ${race.province}` : ""}
          </p>
        </div>
        <div className="text-right text-xs text-slate-400">
          <div>
            <span className="text-base font-semibold text-slate-100">
              {race.pct_reporting != null ? <Num value={race.pct_reporting} suffix="%" /> : "—"}
            </span>{" "}
            reporting
          </div>
          <div><Num value={total} format /> votes counted</div>
        </div>
      </header>

      <ul className="grid gap-3 sm:grid-cols-2">
        {shown.map((c) => {
          const color = getPartyColor(c.party_code);
          const won = race.winner_party != null && race.winner_party === c.party_code;
          return (
            <li
              key={c.name}
              className="flex items-center gap-4 rounded-lg border border-slate-800 bg-slate-950/40 p-3"
            >
              <CandidateAvatar
                name={c.name}
                partyCode={c.party_code}
                state={race.province}
                size={64}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-semibold text-slate-100">{c.name}</span>
                  <span className="rounded px-1.5 text-[11px] font-bold text-white" style={{ backgroundColor: color }}>
                    {c.party_code}
                  </span>
                  {won && (
                    <span className="text-xs text-emerald-400" title="Winner flag from civicAPI, not our call">
                      ✓ civicAPI call
                    </span>
                  )}
                </div>
                <div className="mt-1 flex items-baseline justify-between text-sm">
                  <span className="font-mono text-slate-200"><Num value={c.pct} decimals={1} suffix="%" /></span>
                  <span className="font-mono text-xs text-slate-400"><Num value={c.votes} format /></span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded bg-slate-800">
                  <div className="bar-anim h-full rounded" style={{ width: `${Math.min(c.pct, 100)}%`, backgroundColor: color }} />
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      {race.candidates.length > shown.length && (
        <p className="mt-3 text-xs text-slate-500">
          + {race.candidates.length - shown.length} more candidates
        </p>
      )}
    </section>
  );
};
