import React from "react";
import { fullRaceLabel } from "../lib/format";
import { CandidateAvatar } from "./CandidateAvatar";
import type { Office, Race } from "../api/types";
import { NeedleGauge } from "./NeedleGauge";

export interface KeyRacesProps {
  office: Office;
  races: Race[] | undefined;
  selectedRaceId: number | null;
  onSelectRace: (raceId: number) => void;
  isLoading: boolean;
  isWaiting: boolean;
  error: Error | null;
}

export const KeyRaces: React.FC<KeyRacesProps> = ({
  office,
  races,
  selectedRaceId,
  onSelectRace,
  isLoading,
  isWaiting,
  error,
}) => {
  return (
    <section
      aria-label={`Key ${office} races`}
      className="flex flex-col rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
          Key Races — {office.toUpperCase()}
        </h2>
        <span className="text-xs text-slate-400">
          Click a race for margin history
        </span>
      </div>

      {isLoading ? (
        <div className="space-y-2.5">
          {[0, 1, 2, 3, 4].map((idx) => (
            <div
              key={idx}
              className="h-20 w-full animate-pulse rounded-lg bg-slate-800/70"
            />
          ))}
        </div>
      ) : isWaiting ? (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-slate-800 py-12">
          <p className="text-sm text-slate-400">Waiting for first results</p>
        </div>
      ) : error ? (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-slate-800 py-8">
          <p className="text-xs text-rose-400">{error.message}</p>
        </div>
      ) : !races || races.length === 0 ? (
        <div className="flex flex-1 items-center justify-center rounded-lg border border-slate-800 py-12">
          <p className="text-xs text-slate-400">No tracked races for {office}</p>
        </div>
      ) : (
        <div className="max-h-[540px] space-y-2 overflow-y-auto pr-1">
          {races.map((race) => {
            const topTwo = race.candidates.slice(0, 2);
            const isSelected = race.race_id === selectedRaceId;
            const hasProjection =
              race.projection.status === "ok" &&
              race.projection.median !== null &&
              race.projection.p10 !== null &&
              race.projection.p90 !== null;

            return (
              <div
                key={race.race_id}
                role="button"
                tabIndex={0}
                aria-pressed={isSelected}
                onClick={() => onSelectRace(race.race_id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelectRace(race.race_id);
                  }
                }}
                className={`lift flex cursor-pointer items-center justify-between gap-3 rounded-lg border p-3 transition-colors ${
                  isSelected
                    ? "border-blue-500/80 bg-slate-800/90"
                    : "border-slate-800 bg-slate-950/60 hover:border-slate-700 hover:bg-slate-800/40"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="mb-1.5 flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs font-bold text-slate-100">
                      {fullRaceLabel(race.label)}
                    </span>
                    <span className="text-[11px] text-slate-400">
                      {race.pct_reporting !== null
                        ? `${race.pct_reporting.toFixed(0)}% reporting`
                        : "0% reporting"}
                    </span>
                    {race.winner_party && (
                      <span
                        className="inline-flex items-center gap-1 rounded bg-emerald-950/90 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300 ring-1 ring-emerald-700/60"
                        title={`Winner flagged by civicAPI (${race.winner_party})`}
                      >
                        <span aria-hidden="true">✓</span>
                        civicAPI call ({race.winner_party})
                      </span>
                    )}
                  </div>

                  <div className="space-y-1">
                    {topTwo.map((cand) => {
                      const isWinner =
                        race.winner_party !== null &&
                        race.winner_party === cand.party_code;

                      return (
                        <div
                          key={`${race.race_id}-${cand.name}`}
                          className="flex items-center justify-between gap-2 text-xs"
                        >
                          <div className="flex min-w-0 items-center gap-1.5">
                            <CandidateAvatar
                              name={cand.name}
                              partyCode={cand.party_code}
                              state={race.province}
                              size={24}
                            />
                            <span className="truncate font-medium text-slate-200">
                              {cand.name}
                            </span>
                            <span className="font-mono text-[11px] text-slate-400">
                              ({cand.party_code})
                            </span>
                            {isWinner && (
                              <span
                                className="text-emerald-400"
                                aria-label="civicAPI call winner"
                              >
                                ✓
                              </span>
                            )}
                          </div>

                          <div className="flex shrink-0 items-center gap-2 font-mono text-xs">
                            <span className="text-slate-400">
                              {cand.votes.toLocaleString("en-US")}
                            </span>
                            <span className="w-12 text-right font-semibold text-slate-100">
                              {cand.pct.toFixed(1)}%
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="flex w-24 shrink-0 flex-col items-center justify-center border-l border-slate-800/80 pl-2">
                  {hasProjection ? (
                    <NeedleGauge
                      median={race.projection.median as number}
                      p10={race.projection.p10 as number}
                      p90={race.projection.p90 as number}
                    />
                  ) : (
                    <span className="text-center text-[11px] font-medium text-slate-400">
                      Counts only
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};
