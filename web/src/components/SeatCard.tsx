import React from "react";
import type { Summary } from "../api/types";
import { seatSegments } from "../lib/format";
import { PARTY_COLORS } from "../lib/scales";

export interface SeatCardProps {
  title: string;
  summary: Summary | undefined;
  isLoading: boolean;
  isWaiting: boolean;
  error: Error | null;
}

export const SeatCard: React.FC<SeatCardProps> = ({
  title,
  summary,
  isLoading,
  isWaiting,
  error,
}) => {
  if (isLoading) {
    return (
      <section className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow">
        <div className="h-4 w-24 animate-pulse rounded bg-slate-800" />
        <div className="my-4 h-6 w-full animate-pulse rounded-md bg-slate-800" />
        <div className="flex justify-between">
          <div className="h-4 w-16 animate-pulse rounded bg-slate-800" />
          <div className="h-4 w-16 animate-pulse rounded bg-slate-800" />
        </div>
      </section>
    );
  }

  if (isWaiting) {
    return (
      <section className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          {title}
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
          {title}
        </h2>
        <p className="my-4 text-xs text-rose-400">
          {error?.message ?? "Unable to load summary"}
        </p>
      </section>
    );
  }

  const breakdown = seatSegments(summary);

  return (
    <section
      aria-label={`${title} seat balance`}
      className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          {title}
        </h2>
        {breakdown.majority_line !== null && (
          <span className="text-xs text-slate-400">
            Majority:{" "}
            <strong className="font-mono text-slate-200">
              {breakdown.majority_line}
            </strong>{" "}
            / {breakdown.total}
          </span>
        )}
      </div>

      <div className="relative my-3.5">
        <div className="flex h-6 w-full overflow-hidden rounded-md bg-slate-800 ring-1 ring-slate-700/80">
          {breakdown.segments.map((seg) =>
            seg.count > 0 ? (
              <div
                key={seg.key}
                style={{
                  width: `${seg.pct}%`,
                  backgroundColor: seg.color,
                }}
                title={`${seg.label}: ${seg.count}`}
                className="h-full transition-all duration-300"
              />
            ) : null
          )}
        </div>

        {breakdown.majorityPct !== null && (
          <div
            style={{ left: `${breakdown.majorityPct}%` }}
            className="pointer-events-none absolute -bottom-1 -top-1 w-0.5 -translate-x-1/2 bg-white shadow-[0_0_4px_rgba(255,255,255,0.9)]"
            aria-label={`Majority line at ${breakdown.majority_line} seats`}
          />
        )}
      </div>

      <div className="grid grid-cols-4 gap-1 text-xs">
        <div className="flex flex-col">
          <span className="flex items-center gap-1 text-slate-400">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ backgroundColor: PARTY_COLORS.D }}
              aria-hidden="true"
            />
            D
          </span>
          <span className="font-mono text-sm font-bold text-slate-100">
            {breakdown.d_total}
          </span>
        </div>

        <div className="flex flex-col">
          <span className="flex items-center gap-1 text-slate-400">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ backgroundColor: PARTY_COLORS.O }}
              aria-hidden="true"
            />
            I/O
          </span>
          <span className="font-mono text-sm font-bold text-slate-100">
            {breakdown.o_total}
          </span>
        </div>

        <div className="flex flex-col">
          <span className="flex items-center gap-1 text-slate-400">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ backgroundColor: PARTY_COLORS.UNCALLED }}
              aria-hidden="true"
            />
            Uncalled
          </span>
          <span className="font-mono text-sm font-bold text-slate-300">
            {breakdown.uncalled}
          </span>
        </div>

        <div className="flex flex-col text-right">
          <span className="flex items-center justify-end gap-1 text-slate-400">
            R
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ backgroundColor: PARTY_COLORS.R }}
              aria-hidden="true"
            />
          </span>
          <span className="font-mono text-sm font-bold text-slate-100">
            {breakdown.r_total}
          </span>
        </div>
      </div>
    </section>
  );
};
