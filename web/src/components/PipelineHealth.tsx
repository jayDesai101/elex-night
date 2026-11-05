import React, { useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip } from "recharts";
import type { Check, PipelineInfo } from "../api/types";
import { formatET } from "../lib/format";

export interface PipelineHealthProps {
  pipeline: PipelineInfo | undefined;
  isLoading: boolean;
  isWaiting: boolean;
  error: Error | null;
}

function getCheckStyles(status: Check["status"]): {
  dot: string;
  badge: string;
  label: string;
} {
  if (status === "pass") {
    return {
      dot: "bg-emerald-400",
      badge: "text-emerald-300 bg-emerald-950/70 border-emerald-800/60",
      label: "PASS",
    };
  }
  if (status === "warn") {
    return {
      dot: "bg-amber-400",
      badge: "text-amber-300 bg-amber-950/70 border-amber-800/60",
      label: "WARN",
    };
  }
  // Both "fail" and "error" use red dot
  return {
    dot: "bg-rose-500",
    badge: "text-rose-300 bg-rose-950/70 border-rose-800/60",
    label: status.toUpperCase(),
  };
}

export const PipelineHealth: React.FC<PipelineHealthProps> = ({
  pipeline,
  isLoading,
  isWaiting,
  error,
}) => {
  const [showAll, setShowAll] = useState(false);
  const checks = pipeline?.checks ?? [];
  const passed = checks.filter((c) => c.status === "pass").length;
  const warned = checks.filter((c) => c.status === "warn").length;
  const failed = checks.length - passed - warned;
  // Collapsed: only what needs attention; expanded: every check
  const visible = showAll ? checks : checks.filter((c) => c.status !== "pass");
  return (
    <section
      aria-label="Pipeline health and latency"
      className="flex flex-col justify-between rounded-xl border border-slate-800 bg-slate-900/90 p-4 shadow"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
          Pipeline Health
        </h2>
        {pipeline && (
          <span className="font-mono text-xs text-slate-400">
            Ingest: {formatET(pipeline.last_ingest_at)}
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <div className="h-12 w-full animate-pulse rounded bg-slate-800/70" />
          <div className="h-24 w-full animate-pulse rounded bg-slate-800/70" />
          <div className="h-16 w-full animate-pulse rounded bg-slate-800/70" />
        </div>
      ) : isWaiting ? (
        <div className="flex h-64 items-center justify-center rounded-lg border border-dashed border-slate-800">
          <p className="text-sm text-slate-400">Waiting for first results</p>
        </div>
      ) : error || !pipeline ? (
        <div className="flex h-64 items-center justify-center rounded-lg border border-slate-800">
          <p className="text-xs text-rose-400">
            {error?.message ?? "Unable to load pipeline telemetry"}
          </p>
        </div>
      ) : (
        <div className="flex flex-1 flex-col justify-between gap-4">
          <div className="grid grid-cols-2 gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-slate-400">
                Last Ingest (ET)
              </div>
              <div className="mt-0.5 font-mono text-sm font-bold text-slate-100">
                {formatET(pipeline.last_ingest_at)}
              </div>
            </div>
            <div>
              <div className="text-[11px] uppercase tracking-wider text-slate-400">
                Rows Processed
              </div>
              <div className="mt-0.5 font-mono text-sm font-bold text-slate-100">
                {pipeline.rows_processed.toLocaleString("en-US")}
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs font-semibold text-slate-400">
              <span>Data Integrity Checks</span>
              <button
                type="button"
                onClick={() => setShowAll((v) => !v)}
                className="min-h-[36px] rounded px-2.5 py-1.5 text-blue-400 hover:bg-slate-800"
              >
                {showAll ? "Show less" : `Show all ${checks.length}`}
              </button>
            </div>
            <div className="flex flex-wrap gap-1.5 text-[11px] font-semibold">
              <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-emerald-400">
                {passed} passed
              </span>
              {warned > 0 && (
                <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-400">
                  {warned} warning{warned > 1 ? "s" : ""}
                </span>
              )}
              {failed > 0 && (
                <span className="rounded-full bg-rose-500/15 px-2 py-0.5 text-rose-400">
                  {failed} failing
                </span>
              )}
            </div>
            <ul className="space-y-1.5">
              {visible.map((chk) => {
                const style = getCheckStyles(chk.status);
                return (
                  <li
                    key={chk.name}
                    className="flex items-center justify-between gap-2 rounded-md border border-slate-800/80 bg-slate-950/50 px-2.5 py-1.5 text-xs"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <span
                        className={`h-2.5 w-2.5 shrink-0 rounded-full ${style.dot}`}
                        aria-hidden="true"
                      />
                      <span className="truncate font-mono text-slate-200">
                        {chk.name}
                      </span>
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                      {chk.detail && (
                        <span className="max-w-[140px] truncate text-[11px] text-slate-400">
                          {chk.detail}
                        </span>
                      )}
                      <span
                        className={`rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold ${style.badge}`}
                      >
                        {style.label}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between text-xs text-slate-400">
              <span>Ingest Latency (p50 ms)</span>
              {pipeline.latency.length > 0 && (
                <span className="font-mono text-slate-200">
                  {pipeline.latency[pipeline.latency.length - 1]?.p50_ms ?? "—"}{" "}
                  ms
                </span>
              )}
            </div>
            <div className="h-16 w-full rounded-md border border-slate-800/80 bg-slate-950/60 p-1.5">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={pipeline.latency}>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      borderColor: "#334155",
                      borderRadius: "0.375rem",
                      fontSize: "11px",
                    }}
                    // No x-axis, so the label is the point's index: read the time from
                    // the hovered point instead.
                    labelFormatter={(_: unknown, items: ReadonlyArray<{ payload?: { t?: string } }>) =>
                      formatET(items?.[0]?.payload?.t)
                    }
                    formatter={(val: unknown) => [
                      typeof val === "number" ? `${Math.round(val).toLocaleString("en-US")} ms` : "—",
                      "p50",
                    ]}
                  />
                  <Line
                    type="monotone"
                    dataKey="p50_ms"
                    stroke="#38bdf8"
                    strokeWidth={1.75}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
