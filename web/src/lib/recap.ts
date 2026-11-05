import type { MapCounty, Recap } from "../api/types";

/** Number of recap rows at or before t (rows are sorted by t). */
export function rowsUpTo(t: number[], at: number): number {
  let lo = 0;
  let hi = t.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (t[mid] <= at) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/**
 * The county map as it stood at `at` (epoch seconds): each race's latest update per county,
 * summed over races (House districts split counties). Names, states and the 2024 baseline
 * come from the live map; counties with no result yet are left out, as on the live map.
 */
export function mapAt(rc: Recap, at: number, live: MapCounty[] | undefined): MapCounty[] {
  const n = rowsUpTo(rc.t, at);
  const latest = new Map<string, number>(); // race|fips -> row
  for (let i = 0; i < n; i++) latest.set(`${rc.race_id[i]}|${rc.fips[i]}`, i);

  const sums = new Map<string, { d: number; r: number; total: number; pct: number[] }>();
  for (const i of latest.values()) {
    const s = sums.get(rc.fips[i]) ?? { d: 0, r: 0, total: 0, pct: [] };
    s.d += rc.d[i];
    s.r += rc.r[i];
    s.total += rc.total[i];
    const p = rc.pct[i];
    if (p !== null) s.pct.push(p);
    sums.set(rc.fips[i], s);
  }

  const meta = new Map((live ?? []).map((c) => [c.fips, c]));
  const out: MapCounty[] = [];
  for (const [fips, s] of sums) {
    const m = meta.get(fips);
    out.push({
      fips,
      county_name: m?.county_name ?? null,
      state_po: m?.state_po ?? null,
      margin_pp: s.d + s.r > 0 ? (100 * (s.d - s.r)) / (s.d + s.r) : null,
      pct_reporting: s.pct.length ? s.pct.reduce((a, b) => a + b, 0) / s.pct.length : null,
      total_votes: s.total,
      baseline_margin_pp: m?.baseline_margin_pp ?? null,
    });
  }
  return out;
}
