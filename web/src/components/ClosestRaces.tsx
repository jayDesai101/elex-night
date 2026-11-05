import React, { useMemo } from "react";
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useRaces } from "../api/client";
import type { Office } from "../api/types";
import { fullRaceLabel, marginLabel } from "../lib/format";
import { PARTY_COLORS } from "../lib/scales";

const LIMIT = 8;

/** The tightest races in the active office (any race with votes, not only key races). */
export const ClosestRaces: React.FC<{ office: Office; onSelectRace?: (id: number) => void }> = ({
  office,
  onSelectRace,
}) => {
  const q = useRaces(office, false);
  const narrow = typeof window !== "undefined" && window.innerWidth < 640;
  const rows = useMemo(
    () =>
      (q.data ?? [])
        .filter((r) => r.margin_pp !== null && r.candidates.some((c) => c.votes > 0))
        .sort((a, b) => Math.abs(a.margin_pp as number) - Math.abs(b.margin_pp as number))
        .slice(0, LIMIT)
        .map((r) => ({
          id: r.race_id,
          name: office === "house" && r.district ? r.district : fullRaceLabel(r.label),
          gap: Math.abs(r.margin_pp as number),
          margin: r.margin_pp as number,
          reporting: r.pct_reporting ?? 0,
        })),
    [q.data, office]
  );

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-200">
          Closest {office} races
        </h2>
        <span className="text-xs text-slate-400">Two-party margin, points</span>
      </div>
      {rows.length === 0 ? (
        <div className="flex h-56 items-center justify-center rounded-lg border border-dashed border-slate-800 text-sm text-slate-400">
          The tightest races show up here once votes are counted
        </div>
      ) : (
        <div style={{ height: Math.max(80, rows.length * 36) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 56, left: 8, bottom: 0 }}>
              <XAxis type="number" hide domain={[0, "dataMax"]} />
              <YAxis
                type="category"
                dataKey="name"
                width={narrow ? 104 : 150}
                stroke="#94a3b8"
                fontSize={narrow ? 11 : 12}
                tickLine={false}
                axisLine={false}
                tickFormatter={(n: string) => (narrow && n.length > 16 ? `${n.slice(0, 15)}…` : n)}
              />
              <Tooltip
                cursor={{ fill: "rgba(148,163,184,0.08)" }}
                contentStyle={{ background: "#0f172a", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
                formatter={(_: number, __: string, item: { payload?: { margin: number; reporting: number } }) => [
                  `${marginLabel(item.payload?.margin ?? null)} · ${(item.payload?.reporting ?? 0).toFixed(0)}% in`,
                  "Margin",
                ]}
              />
              <Bar dataKey="gap" barSize={20} radius={[0, 6, 6, 0]} onClick={(d: { id?: number }) => d.id && onSelectRace?.(d.id)} className="cursor-pointer">
                {rows.map((r) => (
                  <Cell key={r.id} fill={r.margin >= 0 ? PARTY_COLORS.D : PARTY_COLORS.R} />
                ))}
                <LabelList dataKey="margin" position="right" formatter={(v: number) => marginLabel(v)} fill="#cbd5e1" fontSize={12} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
};
