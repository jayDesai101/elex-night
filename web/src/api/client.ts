import { useQuery, UseQueryResult } from "@tanstack/react-query";
import { currentStep, inReplay, loadIndex, modeKey, replayPath } from "../lib/replay";
import type {
  Health,
  HistoryPoint,
  MapCounty,
  Office,
  PipelineInfo,
  Race,
  Recap,
  Summary,
  VotePoint,
} from "./types";

export const POLL_INTERVAL_MS = 30_000;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;

  constructor(status: number, message: string, detail: string | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function isWaitingForResults(error: unknown): boolean {
  return error instanceof ApiError && error.status === 503;
}

async function fetchJson<T>(path: string): Promise<T> {
  if (inReplay()) {
    // Replay: the static snapshot for the current step instead of the live API
    const index = await loadIndex();
    const key = index.keys[Math.min(currentStep(), index.keys.length - 1)];
    if (!key) throw new ApiError(503, "no data yet", "no data yet");
    path = replayPath(path, key);
  }
  const response = await fetch(path, {
    method: "GET",
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    let detail: string | null = null;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body?.detail === "string") {
        detail = body.detail;
      }
    } catch {
      // Ignore JSON parse errors on non-JSON error responses
    }
    throw new ApiError(
      response.status,
      detail ?? `Request failed (${response.status})`,
      detail
    );
  }

  return (await response.json()) as T;
}

export function fetchHealth(): Promise<Health> {
  return fetchJson<Health>("/api/health");
}

export function fetchSummary(office?: Office): Promise<Summary[]> {
  const query = office ? `?office=${encodeURIComponent(office)}` : "";
  return fetchJson<Summary[]>(`/api/summary${query}`);
}

export function fetchMap(office: Office): Promise<MapCounty[]> {
  return fetchJson<MapCounty[]>(`/api/map?office=${encodeURIComponent(office)}`);
}

export function fetchRecap(office: Office): Promise<Recap> {
  return fetchJson<Recap>(`/api/recap?office=${encodeURIComponent(office)}`);
}

export function fetchRaces(office: Office, tracked = true): Promise<Race[]> {
  const params = new URLSearchParams({
    office,
    tracked: String(tracked),
  });
  return fetchJson<Race[]>(`/api/races?${params.toString()}`);
}

export function fetchAllRaces(): Promise<Race[]> {
  return fetchJson<Race[]>("/api/races");
}

export function fetchRaceHistory(raceId: number): Promise<HistoryPoint[]> {
  return fetchJson<HistoryPoint[]>(
    `/api/races/${encodeURIComponent(String(raceId))}/history`
  );
}

export function fetchPipeline(): Promise<PipelineInfo> {
  return fetchJson<PipelineInfo>("/api/pipeline");
}

/** Replay steps change only the last key part (modeKey). Keep the previous step's data
 * on screen while the next one loads, so numbers, bars and the map update in place instead
 * of flashing skeletons; a different office or race still starts empty. */
function keepAcrossSteps<T>(key: readonly unknown[]) {
  return (prev: T | undefined, prevQuery?: { queryKey: readonly unknown[] }): T | undefined =>
    prevQuery &&
    prevQuery.queryKey.length === key.length &&
    key.slice(0, -1).every((k, i) => k === prevQuery.queryKey[i])
      ? prev
      : undefined;
}

function shouldRetry(failureCount: number, error: Error): boolean {
  if (isWaitingForResults(error)) {
    return false;
  }
  return failureCount < 2;
}

export function useHealth(): UseQueryResult<Health, Error> {
  return useQuery({
    queryKey: ["health", modeKey()],
    placeholderData: keepAcrossSteps(["health", modeKey()]),
    queryFn: fetchHealth,
    refetchInterval: inReplay() ? false : POLL_INTERVAL_MS,
    retry: shouldRetry,
  });
}

export function useSummary(office?: Office): UseQueryResult<Summary[], Error> {
  return useQuery({
    queryKey: ["summary", office ?? "all", modeKey()],
    placeholderData: keepAcrossSteps(["summary", office ?? "all", modeKey()]),
    queryFn: () => fetchSummary(office),
    refetchInterval: inReplay() ? false : POLL_INTERVAL_MS,
    retry: shouldRetry,
  });
}

export function useMap(office: Office): UseQueryResult<MapCounty[], Error> {
  return useQuery({
    queryKey: ["map", office, modeKey()],
    placeholderData: keepAcrossSteps(["map", office, modeKey()]),
    queryFn: () => fetchMap(office),
    refetchInterval: inReplay() ? false : POLL_INTERVAL_MS,
    retry: shouldRetry,
  });
}

/** Loaded only while the recap is open; one fetch per open, no polling. */
export function useRecap(office: Office, enabled: boolean): UseQueryResult<Recap, Error> {
  return useQuery({
    queryKey: ["recap", office, modeKey()],
    placeholderData: keepAcrossSteps(["recap", office, modeKey()]),
    queryFn: () => fetchRecap(office),
    enabled,
    staleTime: 60_000,
    retry: shouldRetry,
  });
}

export function useRaces(
  office: Office,
  tracked = true
): UseQueryResult<Race[], Error> {
  return useQuery({
    queryKey: ["races", office, tracked, modeKey()],
    placeholderData: keepAcrossSteps(["races", office, tracked, modeKey()]),
    queryFn: () => fetchRaces(office, tracked),
    refetchInterval: inReplay() ? false : POLL_INTERVAL_MS,
    retry: shouldRetry,
  });
}

export function useRaceHistory(
  raceId: number | null
): UseQueryResult<HistoryPoint[], Error> {
  return useQuery({
    queryKey: ["raceHistory", raceId, modeKey()],
    placeholderData: keepAcrossSteps(["raceHistory", raceId, modeKey()]),
    queryFn: () => fetchRaceHistory(raceId as number),
    enabled: raceId !== null,
    refetchInterval: inReplay() ? false : POLL_INTERVAL_MS,
    retry: shouldRetry,
  });
}

export function usePipeline(): UseQueryResult<PipelineInfo, Error> {
  return useQuery({
    queryKey: ["pipeline", modeKey()],
    placeholderData: keepAcrossSteps(["pipeline", modeKey()]),
    queryFn: fetchPipeline,
    refetchInterval: inReplay() ? false : POLL_INTERVAL_MS,
    retry: shouldRetry,
  });
}

/** Every race (all offices), for the state drawer; only fetched while a state is open. */
export function useAllRaces(enabled: boolean): UseQueryResult<Race[], Error> {
  return useQuery({
    queryKey: ["races", "all", modeKey()],
    placeholderData: keepAcrossSteps(["races", "all", modeKey()]),
    queryFn: fetchAllRaces,
    enabled,
    refetchInterval: inReplay() || !enabled ? false : POLL_INTERVAL_MS,
    retry: shouldRetry,
  });
}

export function useRaceVotes(raceId: number | null): UseQueryResult<VotePoint[], Error> {
  return useQuery({
    queryKey: ["raceVotes", raceId, modeKey()],
    placeholderData: keepAcrossSteps(["raceVotes", raceId, modeKey()]),
    queryFn: () => fetchJson<VotePoint[]>(`/api/races/${raceId}/votes`),
    enabled: raceId !== null,
    refetchInterval: inReplay() ? false : POLL_INTERVAL_MS,
    retry: shouldRetry,
  });
}
