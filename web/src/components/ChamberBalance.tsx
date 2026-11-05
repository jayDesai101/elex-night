import React from "react";
import type { Summary } from "../api/types";
import { seatSegments } from "../lib/format";
import { useCountUp } from "../lib/useCountUp";

export interface ChamberBalanceProps {
  title: string;
  summary: Summary | undefined;
  isLoading: boolean;
  isWaiting: boolean;
  error: Error | null;
}

const Big: React.FC<{ value: number; className: string }> = ({ value, className }) => {
  const v = useCountUp(value);
  return <span className={`font-extrabold tabular-nums ${className}`}>{Math.round(v)}</span>;
};

/** TV-style balance of power: D | Ind | uncalled | R with a "N to win" marker. */
export const ChamberBalance: React.FC<ChamberBalanceProps> = ({
  title,
  summary,
  isLoading,
  isWaiting,
  error,
}) => {
  const shell = "h-full rounded-xl border border-slate-800 bg-slate-900/80 p-4 shadow";
  if (isLoading) return <div className={`${shell} animate-pulse`} style={{ minHeight: 150 }} />;
  if (isWaiting || !summary)
    return (
      <div className={`${shell} flex items-center justify-center text-sm text-slate-400`}>
        Waiting for first results
      </div>
    );
  if (error) return <div className={`${shell} text-xs text-rose-400`}>{error.message}</div>;

  const s = seatSegments(summary);
  return (
    <section className={`${shell} lift`} aria-label={`${title} balance of power`}>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">{title}</h2>
        {s.majority_line !== null && (
          <span className="text-xs text-slate-400">{s.majority_line} to win</span>
        )}
      </div>
      <div className="flex items-end justify-between">
        <div>
          <Big value={s.d_total} className="text-4xl text-blue-500" />
          <div className="text-[11px] font-semibold uppercase tracking-wide text-blue-400">Dem</div>
        </div>
        <div className="pb-1 text-center text-xs text-slate-400">
          <div className="font-mono text-sm text-slate-300">{s.uncalled}</div>
          uncalled
          {s.o_total > 0 && <div className="text-[11px]">{s.o_total} Ind/Oth</div>}
        </div>
        <div className="text-right">
          <Big value={s.r_total} className="text-4xl text-red-500" />
          <div className="text-[11px] font-semibold uppercase tracking-wide text-red-400">Rep</div>
        </div>
      </div>
      <div className="relative mt-3 h-4 w-full overflow-hidden rounded-full bg-slate-800">
        <div className="flex h-full w-full">
          {s.segments.map((seg) => (
            <div
              key={seg.key}
              style={{ width: `${seg.pct}%`, backgroundColor: seg.color }}
              className="bar-anim h-full"
              title={`${seg.label}: ${seg.count}`}
            />
          ))}
        </div>
        {s.majorityPct !== null && (
          <div
            className="absolute top-[-2px] h-[20px] w-0.5 bg-white shadow"
            style={{ left: `${s.majorityPct}%` }}
            aria-hidden="true"
          />
        )}
      </div>
    </section>
  );
};
