import { useQuery } from "@tanstack/react-query";

/** Candidate photos from Wikipedia's REST summary API (CORS-enabled, no key).
 * Only accepted when the page clearly describes a politician, so a common name never
 * shows the wrong person; otherwise the UI falls back to party-colored initials. */

const POLITICIAN =
  /politician|senator|governor|representative|congress|lieutenant governor|attorney general|secretary of state|state (house|senate)|legislator|mayor|candidate/i;

export function initials(name: string): string {
  const parts = name
    .replace(/\b(jr|sr|ii|iii|iv)\.?$/i, "")
    .replace(/[^\p{L}\s'-]/gu, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0][0].toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function wikiTitle(name: string): string {
  return encodeURIComponent(name.trim().replace(/\s+/g, "_"));
}

interface WikiSummary {
  type?: string;
  description?: string;
  extract?: string;
  thumbnail?: { source: string };
}

export function acceptPhoto(s: WikiSummary | null): string | null {
  if (!s || s.type !== "standard" || !s.thumbnail?.source) return null;
  const text = `${s.description ?? ""} ${(s.extract ?? "").slice(0, 300)}`;
  return POLITICIAN.test(text) ? s.thumbnail.source : null;
}

export const STATES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California",
  CO: "Colorado", CT: "Connecticut", DE: "Delaware", FL: "Florida", GA: "Georgia",
  HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa", KS: "Kansas",
  KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland", MA: "Massachusetts",
  MI: "Michigan", MN: "Minnesota", MS: "Mississippi", MO: "Missouri", MT: "Montana",
  NE: "Nebraska", NV: "Nevada", NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico",
  NY: "New York", NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma",
  OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina",
  SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont",
  VA: "Virginia", WA: "Washington", WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming",
};

/** Titles to try in order: the plain name, then Wikipedia's disambiguated forms. */
export function titleCandidates(name: string, state?: string | null): string[] {
  const base = name.trim().replace(/\s+/g, " ");
  const st = state ? STATES[state] : undefined;
  return [
    base,
    ...(st ? [`${base} (${st} politician)`] : []),
    `${base} (politician)`,
    `${base} (American politician)`,
    `${base} (U.S. senator)`,
  ];
}

async function fetchPhoto(name: string, state?: string | null): Promise<string | null> {
  for (const title of titleCandidates(name, state)) {
    const res = await fetch(
      `https://en.wikipedia.org/api/rest_v1/page/summary/${wikiTitle(title)}`,
      { headers: { Accept: "application/json" } }
    );
    if (!res.ok) continue;
    const photo = acceptPhoto((await res.json()) as WikiSummary);
    if (photo) return photo;
  }
  return null;
}

export function usePhoto(name: string | null | undefined, state?: string | null) {
  return useQuery({
    queryKey: ["photo", name, state ?? null],
    queryFn: () => fetchPhoto(name as string, state),
    enabled: !!name && !/^write[- ]?in/i.test(name),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
  });
}
