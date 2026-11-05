import React from "react";
import { fullRaceLabel } from "../lib/format";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { HistoryPoint, Race } from "../api/types";
import { formatET, marginLabel } from "../lib/format";
import { PARTY_COLORS } from "../lib/scales";

export interface MarginChartProps {
  race: Race | undefined;
  history: HistoryPoint[] | undefined;
  isLoading: boolean;
  isWaiting: boolean;
  error: Error | null;
}

export const MarginChart: React.FC<MarginChartProps> = ({
  race,
  history,
  isLoading,
  isWaiting,
  error,
}) => {
  const validHistory = (history ?? []).filter(
    (pt) => pt.median !== null && pt.p10 !== null && pt.p90 !== null
  );

  return (
    <section
      aria-label="Race margin projection history"
      className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow"
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
            Projected Margin Over Time{" "}
            {race ? `— ${fullRaceLabel(race.label)}` : ""}
          </h2>
          <p className="text-xs text-slate-400">
            Median projected margin (pp) with 10th–90th percentile band (D &gt; 0, R &lt; 0)
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="h-64 w-full animate-pulse rounded-lg bg-slate-800/70" />
      ) : isWaiting ? (
        <div className="flex h-64 w-full items-center justify-center rounded-lg border border-dashed border-slate-800 bg-slate-950/50">
          <p className="text-sm text-slate-400">Waiting for first results</p>
        </div>
      ) : error ? (
        <div className="flex h-64 w-full items-center justify-center rounded-lg border border-slate-800 bg-slate-950/50">
          <p className="text-xs text-rose-400">{error.message}</p>
        </div>
      ) : validHistory.length === 0 ? (
        <div className="flex h-64 w-full items-center justify-center rounded-lg border border-dashed border-slate-800 bg-slate-950/50">
          <p className="text-sm text-slate-400">
            Projection starts once enough counties report
          </p>
        </div>
      ) : (
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart
              data={validHistory}
              margin={{ top: 10, right: 16, bottom: 8, left: 0 }}
            >
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis
                dataKey="as_of"
                tickFormatter={(iso: string) => formatET(iso)}
                stroke="#94a3b8"
                fontSize={11}
                minTickGap={24}
              />
              <YAxis
                stroke="#94a3b8"
                fontSize={11}
                tickFormatter={(val: number) => marginLabel(val)}
              />
              <ReferenceLine
                y={0}
                stroke="#cbd5e1"
                strokeDasharray="4 4"
                strokeWidth={1.2}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#334155",
                  borderRadius: "0.5rem",
                  fontSize: "12px",
                }}
                labelFormatter={(iso) => `Time: ${formatET(String(iso))}`}
                formatter={(value: unknown, name: string) => {
                  if (Array.isArray(value) && value.length === 2) {
                    return [
                      `${marginLabel(Number(value[0]))} to ${marginLabel(
                        Number(value[1])
                      )}`,
                      "p10–p90 Band",
                    ];
                  }
                  if (typeof value === "number") {
                    return [marginLabel(value), name === "median" ? "Median" : name];
                  }
                  return ["—", name];
                }}
              />
              <Area
                type="monotone"
                name="p10-p90"
                dataKey={(pt: HistoryPoint) => [pt.p10, pt.p90]}
                stroke="none"
                fill={PARTY_COLORS.D}
                fillOpacity={0.22}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                name="median"
                dataKey="median"
                stroke={PARTY_COLORS.D}
                strokeWidth={2.2}
                dot={false}
                isAnimationActive={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
};
