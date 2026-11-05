import React from "react";
import type { Office, Summary } from "../api/types";
import { PARTY_COLORS } from "../lib/scales";

export interface ExpectedVoteRingProps {
  office: Office;
  summary: Summary | undefined;
  isLoading: boolean;
  isWaiting: boolean;
  error: Error | null;
}

export const ExpectedVoteRing: React.FC<ExpectedVoteRingProps> = ({
  office,
  summary,
  isLoading,
  isWaiting,
  error,
}) => {
  const isHouse = office === "house";
  const label = isHouse ? "avg. % reporting" : "est. expected vote counted";
  const rawValue = isHouse
    ? summary?.mean_pct_reporting ?? null
    : summary?.est_pct_counted ?? null;

  const clampedPct =
    rawValue !== null && !Number.isNaN(rawValue)
      ? Math.min(100, Math.max(0, rawValue))
      : null;

  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const dashOffset =
    clampedPct !== null
      ? circumference - (clampedPct / 100) * circumference
      : circumference;

  if (isLoading) {
    return (
      <section className="flex items-center gap-4 rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow">
        <div className="h-16 w-16 shrink-0 animate-pulse rounded-full bg-slate-800" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-24 animate-pulse rounded bg-slate-800" />
          <div className="h-3 w-32 animate-pulse rounded bg-slate-800" />
        </div>
      </section>
    );
  }

  if (isWaiting) {
    return (
      <section className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          Vote Progress
        </h2>
        <p className="my-4 text-xs text-slate-400">
          Waiting for first results
        </p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          Vote Progress
        </h2>
        <p className="my-4 text-xs text-rose-400">{error.message}</p>
      </section>
    );
  }

  const displayValue =
    clampedPct === null
      ? "—"
      : `${Number.isInteger(clampedPct) ? clampedPct : clampedPct.toFixed(1)}%`;

  return (
    <section
      aria-label={label}
      className="flex items-center gap-4 rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow"
    >
      <div className="relative flex h-16 w-16 shrink-0 items-center justify-center">
        <svg className="h-16 w-16 -rotate-90" viewBox="0 0 68 68">
          <circle
            cx="34"
            cy="34"
            r={radius}
            fill="none"
            stroke={PARTY_COLORS.NO_DATA}
            strokeWidth="6"
          />
          {clampedPct !== null && (
            <circle
              cx="34"
              cy="34"
              r={radius}
              fill="none"
              stroke={PARTY_COLORS.D}
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={dashOffset}
              className="transition-all duration-500"
            />
          )}
        </svg>
        <span className="absolute font-mono text-xs font-bold text-slate-100">
          {displayValue}
        </span>
      </div>

      <div className="flex flex-col">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          {office}
        </span>
        <span className="font-mono text-lg font-bold text-slate-100">
          {displayValue}
        </span>
        <span className="text-xs text-slate-400">{label}</span>
      </div>
    </section>
  );
};
