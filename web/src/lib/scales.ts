import { scaleDiverging } from "d3-scale";
import { interpolateRdBu } from "d3-scale-chromatic";

export const PARTY_COLORS = {
  D: "#2563eb",
  R: "#dc2626",
  I: "#8b7aa8",
  O: "#8b7aa8",
  UNCALLED: "#475569",
  NO_DATA: "#1e293b",
} as const;

export type PartyKey = keyof typeof PARTY_COLORS;

export function getPartyColor(partyCode: string | null | undefined): string {
  if (!partyCode) {
    return PARTY_COLORS.UNCALLED;
  }
  const normalized = partyCode.toUpperCase();
  if (normalized === "D" || normalized === "DEM") {
    return PARTY_COLORS.D;
  }
  if (normalized === "R" || normalized === "GOP" || normalized === "REP") {
    return PARTY_COLORS.R;
  }
  if (normalized === "I" || normalized === "O" || normalized === "IND") {
    return PARTY_COLORS.I;
  }
  return PARTY_COLORS.UNCALLED;
}

export const countyColorScale = scaleDiverging<string>(
  [-40, 0, 40],
  interpolateRdBu
).clamp(true);

/** Map chrome per theme. Margin colors (RdBu) are the same in both themes; only the
 * no-data fill, borders and highlights change so they read against the background. */
export const MAP_THEME = {
  dark: {
    noData: PARTY_COLORS.NO_DATA,
    countyStroke: "#0f172a",
    stateStroke: "#cbd5e1",
    hoverStroke: "#f8fafc",
    flipped: "#fbbf24",
    shadow: "drop-shadow(0 6px 14px rgba(0,0,0,0.45))",
  },
  light: {
    noData: "#e2e8f0",
    countyStroke: "#ffffff",
    stateStroke: "#475569",
    hoverStroke: "#0f172a",
    flipped: "#d97706",
    shadow: "drop-shadow(0 4px 10px rgba(15,23,42,0.18))",
  },
} as const;

export function getCountyFill(
  marginPp: number | null | undefined,
  noData: string = PARTY_COLORS.NO_DATA
): string {
  if (marginPp === null || marginPp === undefined || Number.isNaN(marginPp)) {
    return noData;
  }
  return countyColorScale(marginPp);
}
