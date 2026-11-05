import React, { useMemo } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useRaceVotes } from "../api/client";
import type { Race } from "../api/types";
import { formatET, fullRaceLabel } from "../lib/format";
import { getPartyColor } from "../lib/scales";

const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const full = new Intl.NumberFormat("en-US");

/** Vote totals over the night for the selected race, one line per leading candidate. */
export const VoteTimeline: React.FC<{ race: Race | null }> = ({ race }) => {
  const q = useRaceVotes(race?.race_id ?? null);
  const { data, lines, hasVotes } = useMemo(() => {
    const pts = q.data ?? [];
    const top = (race?.candidates ?? []).slice(0, 3);
    const byT = new Map<string, Record<string, number | string>>();
    for (const p of pts) {
      if (!top.some((c) => c.name === p.name)) continue;
      const row = byT.get(p.t) ?? { t: p.t };
      row[p.name] = p.votes;
      byT.set(p.t, row);
    }
    const rows = [...byT.values()].sort((a, b) => String(a.t).localeCompare(String(b.t)));
    return { data: rows, lines: top, hasVotes: pts.some((p) => p.votes > 0) };
  }, [q.data, race]);

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
          Vote count over the night{race ? ` — ${fullRaceLabel(race.label)}` : ""}
        </h2>
        <span className="text-xs text-slate-400">{data.length} snapshots archived</span>
      </div>
      {!hasVotes ? (
        <div className="flex h-56 items-center justify-center rounded-lg border border-dashed border-slate-800 text-sm text-slate-400">
          Vote totals appear here as counties report
        </div>
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
              <XAxis dataKey="t" tickFormatter={(t: string) => formatET(t).replace(" ET", "")} stroke="#64748b" fontSize={11} minTickGap={40} />
              <YAxis tickFormatter={(v: number) => compact.format(v)} stroke="#64748b" fontSize={11} width={48} />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
                labelFormatter={(t: string) => formatET(t)}
                formatter={(v: number, name: string) => [full.format(v), name]}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {lines.map((c, i) => (
                <Line
                  key={c.name}
                  type="monotone"
                  dataKey={c.name}
                  stroke={getPartyColor(c.party_code)}
                  strokeWidth={i === 0 ? 3 : 2}
                  strokeOpacity={i === 2 ? 0.6 : 1}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
};
