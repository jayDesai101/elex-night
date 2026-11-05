import React, { useMemo } from "react";
import type { MapCounty, Race } from "../api/types";
import { stateCountyShapes } from "../lib/geo";
import { getCountyFill, getPartyColor, MAP_THEME } from "../lib/scales";
import { useTheme } from "../lib/theme";
import { Num } from "./Num";
import { flashClass } from "../lib/useFlash";

const W = 220;
const H = 150;

/** "Jon Ossoff" -> "Ossoff"; keeps suffixes off ("Daniel J. Jr. Sullivan" -> "Sullivan"). */
export function lastName(name: string): string {
  const parts = name.replace(/\b(jr|sr|ii|iii|iv)\.?/gi, "").trim().split(/\s+/);
  return parts[parts.length - 1] || name;
}

const MiniMap: React.FC<{ po: string; counties: Map<string, MapCounty> }> = ({ po, counties }) => {
  const mt = MAP_THEME[useTheme()];
  const shapes = useMemo(() => stateCountyShapes(po, W, H), [po]);
  if (shapes.length === 0) {
    return (
      <div className="flex h-[150px] items-center justify-center text-xs text-slate-500">
        No county map for {po}
      </div>
    );
  }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-[150px] w-full" role="img" aria-label={`${po} county results`}>
      {shapes.map((s) => (
        <path
          key={s.fips}
          d={s.d}
          fill={getCountyFill(counties.get(s.fips)?.margin_pp ?? null, mt.noData)}
          stroke={mt.countyStroke}
          strokeWidth={0.5}
        />
      ))}
    </svg>
  );
};

const Badge: React.FC<{ code: string }> = ({ code }) => (
  <span
    className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
    style={{ backgroundColor: getPartyColor(code) }}
  >
    {code}
  </span>
);

/** One flash flag per race, keyed on its vote total (hooks cannot live inside the map). */
function useCardFlashes(races: Race[] | undefined): Record<number, boolean> {
  const sig = (races ?? []).map((r) => `${r.race_id}:${r.candidates.reduce((s, c) => s + c.votes, 0)}`).join("|");
  const prev = React.useRef<Map<number, string>>(new Map());
  const [on, setOn] = React.useState<Record<number, boolean>>({});
  React.useEffect(() => {
    const changed: number[] = [];
    const next = new Map<number, string>();
    for (const part of sig ? sig.split("|") : []) {
      const [id, votes] = part.split(":");
      next.set(Number(id), votes);
      const old = prev.current.get(Number(id));
      if (old !== undefined && old !== votes) changed.push(Number(id));
    }
    prev.current = next;
    if (changed.length === 0) return;
    setOn((o) => ({ ...o, ...Object.fromEntries(changed.map((id) => [id, true])) }));
    const t = setTimeout(() => setOn((o) => ({ ...o, ...Object.fromEntries(changed.map((id) => [id, false])) })), 1500);
    return () => clearTimeout(t);
  }, [sig]);
  return on;
}

export interface KeyRaceCardsProps {
  title: string;
  races: Race[] | undefined;
  counties: MapCounty[] | undefined;
  selectedRaceId: number | null;
  onSelectRace: (id: number) => void;
}

/** Key races as cards: state, % reported, a county map of the race, top candidates. */
export const KeyRaceCards: React.FC<KeyRaceCardsProps> = ({
  title,
  races,
  counties,
  selectedRaceId,
  onSelectRace,
}) => {
  const byFips = useMemo(() => {
    const m = new Map<string, MapCounty>();
    for (const c of counties ?? []) m.set(String(c.fips).padStart(5, "0"), c);
    return m;
  }, [counties]);
  const flashes = useCardFlashes(races);
  if (!races || races.length === 0) return null;
  return (
    <section aria-label={title} className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <h2 className="mb-3 text-lg font-bold text-slate-100">{title}</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {races.map((r) => {
          const po = r.province ?? "";
          const top = r.candidates.slice(0, 4);
          const selected = r.race_id === selectedRaceId;
          return (
            <button
              key={r.race_id}
              type="button"
              onClick={() => onSelectRace(r.race_id)}
              aria-pressed={selected}
              className={`lift flex flex-col rounded-2xl border bg-slate-950/50 p-4 text-left ${
                selected ? "border-blue-500" : "border-slate-800"
              } ${flashClass(flashes[r.race_id] ?? false)}`}
            >
              <div className="flex items-baseline justify-between">
                <span className="text-2xl font-extrabold tracking-tight text-slate-100">{po}</span>
                <span className="text-sm text-slate-400">
                  <Num value={r.pct_reporting ?? 0} suffix="%" /> reported
                </span>
              </div>
              <div className="my-2">
                <MiniMap po={po} counties={byFips} />
              </div>
              <ul className="mt-auto space-y-1">
                {top.map((c) => (
                  <li key={c.name} className="flex items-center gap-2 text-sm">
                    <Badge code={c.party_code} />
                    <span className="flex-1 truncate font-medium text-slate-200">
                      {lastName(c.name)}
                      {r.winner_party === c.party_code && c === top[0] && (
                        <span className="ml-1 text-emerald-400" title="Winner flag from civicAPI">✓</span>
                      )}
                    </span>
                    <span className="font-mono font-bold tabular-nums text-slate-100">
                      <Num value={c.pct} suffix="%" />
                    </span>
                  </li>
                ))}
              </ul>
            </button>
          );
        })}
      </div>
    </section>
  );
};
