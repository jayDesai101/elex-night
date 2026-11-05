import React, { useEffect, useState } from "react";
import type { Health, Office } from "../api/types";
import { ageSeconds, formatET, liveState } from "../lib/format";

export interface TopBarProps {
  activeOffice: Office;
  onSelectOffice: (office: Office) => void;
  health: Health | undefined;
  fallbackLastIngestAt?: string | null;
  isLoading?: boolean;
}

const OFFICE_TABS: { id: Office; label: string }[] = [
  { id: "senate", label: "Senate" },
  { id: "house", label: "House" },
  { id: "governor", label: "Governor" },
];

export const TopBar: React.FC<TopBarProps> = ({
  activeOffice,
  onSelectOffice,
  health,
  fallbackLastIngestAt,
  isLoading,
}) => {
  const lastUpdatedIso = health?.last_ingest_at ?? fallbackLastIngestAt ?? null;
  // Age is computed here, against the clock, not taken from the last response: a page that
  // stops getting fresh data (background tab, sleep, failed requests) must not stay LIVE.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 15_000);
    return () => clearInterval(t);
  }, []);
  const badge = liveState(ageSeconds(lastUpdatedIso, now));
  const formattedTime = formatET(lastUpdatedIso);

  const badgeStyles: Record<
    typeof badge.color,
    { container: string; dot: string }
  > = {
    green: {
      container: "bg-emerald-950/80 text-emerald-300 border-emerald-700/60",
      dot: "bg-emerald-400 live-ping",
    },
    amber: {
      container: "bg-amber-950/80 text-amber-300 border-amber-700/60",
      dot: "bg-amber-400",
    },
    red: {
      container: "bg-rose-950/80 text-rose-300 border-rose-700/60",
      dot: "bg-rose-500",
    },
  };

  const currentStyle = badgeStyles[badge.color];

  return (
    <header className="w-full rounded-xl border border-slate-800 bg-slate-900/90 px-4 py-3 shadow-lg backdrop-blur">
      <div className="flex flex-col gap-3 min-[900px]:flex-row min-[900px]:items-center min-[900px]:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2.5">
            <span className="text-lg font-bold tracking-tight text-slate-100">
              Election Night Results
            </span>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wider ${currentStyle.container}`}
              aria-label={`Feed status: ${badge.label}`}
            >
              <span
                className={`h-2 w-2 rounded-full ${currentStyle.dot}`}
                aria-hidden="true"
              />
              {badge.label}
            </span>
          </div>

          <div className="text-xs text-slate-400">
            <span>Last updated: </span>
            {isLoading && !lastUpdatedIso ? (
              <span className="inline-block h-3.5 w-16 animate-pulse rounded bg-slate-800 align-middle" />
            ) : (
              <span className="font-mono font-medium text-slate-200">
                {formattedTime}
              </span>
            )}
          </div>
        </div>

        <nav
          aria-label="Office tabs"
          className="flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-950/80 p-1"
        >
          {OFFICE_TABS.map((tab) => {
            const isActive = activeOffice === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => onSelectOffice(tab.id)}
                className={`flex-1 rounded-md px-3.5 py-1.5 text-xs font-semibold transition-colors min-[900px]:flex-initial ${
                  isActive
                    ? "bg-blue-600 text-white shadow-sm"
                    : "text-slate-400 hover:bg-slate-800/70 hover:text-slate-200"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
};
