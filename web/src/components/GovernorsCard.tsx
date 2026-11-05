import React from "react";
import type { Summary } from "../api/types";
import { PARTY_COLORS } from "../lib/scales";

export interface GovernorsCardProps {
  summary: Summary | undefined;
  isLoading: boolean;
  isWaiting: boolean;
  error: Error | null;
}

export const GovernorsCard: React.FC<GovernorsCardProps> = ({
  summary,
  isLoading,
  isWaiting,
  error,
}) => {
  if (isLoading) {
    return (
      <section className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow">
        <div className="h-4 w-28 animate-pulse rounded bg-slate-800" />
        <div className="my-3 h-7 w-32 animate-pulse rounded bg-slate-800" />
        <div className="h-4 w-full animate-pulse rounded bg-slate-800" />
      </section>
    );
  }

  if (isWaiting) {
    return (
      <section className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          Governors
        </h2>
        <p className="my-4 text-xs text-slate-400">
          Waiting for first results
        </p>
      </section>
    );
  }

  if (error || !summary) {
    return (
      <section className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          Governors
        </h2>
        <p className="my-4 text-xs text-rose-400">
          {error?.message ?? "Unable to load governor summary"}
        </p>
      </section>
    );
  }

  const calledCount =
    summary.d_called + summary.r_called + summary.o_called;
  const totalUp = summary.seats_up;
  const safeTotal = totalUp > 0 ? totalUp : 1;

  const dPct = (summary.d_called / safeTotal) * 100;
  const oPct = (summary.o_called / safeTotal) * 100;
  const rPct = (summary.r_called / safeTotal) * 100;
  const uncalledPct = Math.max(0, 100 - dPct - oPct - rPct);

  return (
    <section
      aria-label="Governors race calls"
      className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          Governors
        </h2>
        <span className="font-mono text-xs font-semibold text-slate-200">
          Called {calledCount} / {totalUp}
        </span>
      </div>

      <div className="my-3.5">
        <div className="flex h-3 w-full overflow-hidden rounded-full bg-slate-800 ring-1 ring-slate-700/80">
          {summary.d_called > 0 && (
            <div
              style={{
                width: `${dPct}%`,
                backgroundColor: PARTY_COLORS.D,
              }}
              title={`D Called: ${summary.d_called}`}
            />
          )}
          {summary.o_called > 0 && (
            <div
              style={{
                width: `${oPct}%`,
                backgroundColor: PARTY_COLORS.O,
              }}
              title={`I/O Called: ${summary.o_called}`}
            />
          )}
          {uncalledPct > 0 && (
            <div
              style={{
                width: `${uncalledPct}%`,
                backgroundColor: PARTY_COLORS.UNCALLED,
              }}
              title={`Uncalled: ${summary.uncalled}`}
            />
          )}
          {summary.r_called > 0 && (
            <div
              style={{
                width: `${rPct}%`,
                backgroundColor: PARTY_COLORS.R,
              }}
              title={`R Called: ${summary.r_called}`}
            />
          )}
        </div>
      </div>

      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ backgroundColor: PARTY_COLORS.D }}
            aria-hidden="true"
          />
          <span className="text-slate-400">D</span>
          <span className="font-mono text-sm font-bold text-slate-100">
            {summary.d_called}
          </span>
        </div>

        {summary.o_called > 0 && (
          <div className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: PARTY_COLORS.O }}
              aria-hidden="true"
            />
            <span className="text-slate-400">I/O</span>
            <span className="font-mono text-sm font-bold text-slate-100">
              {summary.o_called}
            </span>
          </div>
        )}

        <div className="text-slate-400">
          Uncalled:{" "}
          <span className="font-mono font-semibold text-slate-300">
            {summary.uncalled}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-slate-400">R</span>
          <span className="font-mono text-sm font-bold text-slate-100">
            {summary.r_called}
          </span>
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ backgroundColor: PARTY_COLORS.R }}
            aria-hidden="true"
          />
        </div>
      </div>
    </section>
  );
};
