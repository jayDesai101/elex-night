import { STATES } from "./photos";
import type { Summary } from "../api/types";
import { PARTY_COLORS } from "./scales";

export type LiveLabel = "LIVE" | "DELAYED" | "OFFLINE";
export type LiveColor = "green" | "amber" | "red";

export interface LiveStateResult {
  label: LiveLabel;
  color: LiveColor;
}

/**
 * Computes the live badge status from /api/health.age_seconds:
 * <= 180 -> green "LIVE"
 * <= 600 -> amber "DELAYED"
 * otherwise or null -> red "OFFLINE"
 */
export function liveState(
  ageSeconds: number | null | undefined
): LiveStateResult {
  if (
    ageSeconds === null ||
    ageSeconds === undefined ||
    Number.isNaN(ageSeconds) ||
    ageSeconds < 0
  ) {
    return { label: "OFFLINE", color: "red" };
  }
  if (ageSeconds <= 180) {
    return { label: "LIVE", color: "green" };
  }
  if (ageSeconds <= 600) {
    return { label: "DELAYED", color: "amber" };
  }
  return { label: "OFFLINE", color: "red" };
}

const etTimeFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

/**
 * Formats an ISO timestamp string into America/New_York time, e.g. "9:42 PM ET".
 */
export function formatET(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return `${etTimeFormatter.format(date)} ET`;
}

/**
 * Formats a county or race margin (positive = D, negative = R) as "D +14.2" or "R +3.1".
 */
export function marginLabel(marginPp: number | null | undefined): string {
  if (marginPp === null || marginPp === undefined || Number.isNaN(marginPp)) {
    return "—";
  }
  if (marginPp > 0) {
    return `D +${Math.abs(marginPp).toFixed(1)}`;
  }
  if (marginPp < 0) {
    return `R +${Math.abs(marginPp).toFixed(1)}`;
  }
  return "Even 0.0";
}

export interface SeatSegment {
  key: "D" | "O" | "uncalled" | "R";
  label: string;
  count: number;
  pct: number;
  color: string;
}

export interface SeatSegmentsResult {
  d_total: number;
  o_total: number;
  uncalled: number;
  r_total: number;
  total: number;
  majority_line: number | null;
  majorityPct: number | null;
  segments: SeatSegment[];
}

/**
 * Computes the horizontal seat bar segments: D total | O total | uncalled | R total.
 * Guarantees segments sum to 100 (Senate) or 435 (House).
 */
export function seatSegments(
  summary: Pick<
    Summary,
    "office" | "d_total" | "o_total" | "uncalled" | "r_total" | "majority_line"
  >
): SeatSegmentsResult {
  const targetTotal =
    summary.office === "senate"
      ? 100
      : summary.office === "house"
      ? 435
      : summary.d_total + summary.o_total + summary.uncalled + summary.r_total;

  const d_total = Math.max(0, summary.d_total);
  const o_total = Math.max(0, summary.o_total);
  const r_total = Math.max(0, summary.r_total);

  const rawSum = d_total + o_total + summary.uncalled + r_total;
  const uncalled =
    rawSum === targetTotal
      ? summary.uncalled
      : Math.max(0, targetTotal - (d_total + o_total + r_total));

  const total = d_total + o_total + uncalled + r_total;
  const safeTotal = total > 0 ? total : 1;

  const majorityPct =
    summary.majority_line !== null
      ? (summary.majority_line / safeTotal) * 100
      : null;

  const segments: SeatSegment[] = [
    {
      key: "D",
      label: "Dem",
      count: d_total,
      pct: (d_total / safeTotal) * 100,
      color: PARTY_COLORS.D,
    },
    {
      key: "O",
      label: "Ind / Oth",
      count: o_total,
      pct: (o_total / safeTotal) * 100,
      color: PARTY_COLORS.O,
    },
    {
      key: "uncalled",
      label: "Uncalled",
      count: uncalled,
      pct: (uncalled / safeTotal) * 100,
      color: PARTY_COLORS.UNCALLED,
    },
    {
      key: "R",
      label: "GOP",
      count: r_total,
      pct: (r_total / safeTotal) * 100,
      color: PARTY_COLORS.R,
    },
  ];

  return {
    d_total,
    o_total,
    uncalled,
    r_total,
    total,
    majority_line: summary.majority_line,
    majorityPct,
    segments,
  };
}

/** "AK-Sen" -> "Alaska Senate", "AZ-Gov" -> "Arizona Governor"; other labels unchanged. */
export function fullRaceLabel(label: string): string {
  const m = /^([A-Z]{2})-(Sen|Gov)$/.exec(label.trim());
  if (!m) return label;
  return `${STATES[m[1]] ?? m[1]} ${m[2] === "Sen" ? "Senate" : "Governor"}`;
}

/** Seconds since an ISO time, or null when there is none. */
export function ageSeconds(iso: string | null | undefined, nowMs: number): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : Math.max(0, (nowMs - t) / 1000);
}

/** Spotlight starts on the closest race that has votes, not the first alphabetically
 * (Alaska, whose polls close last). Falls back to the first race. */
export function defaultRace<T extends { candidates: { votes: number }[]; margin_pp: number | null }>(
  list: T[]
): T {
  const counting = list.filter((r) => r.margin_pp !== null && r.candidates.some((c) => c.votes > 0));
  if (counting.length === 0) return list[0];
  return counting.reduce((a, b) =>
    Math.abs(b.margin_pp as number) < Math.abs(a.margin_pp as number) ? b : a
  );
}
