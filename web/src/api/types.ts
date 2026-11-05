export type Office = "senate" | "house" | "governor";
export interface Health { status: "ok"|"delayed"|"offline"; last_ingest_at: string|null;
  serving_version: string; age_seconds: number|null }
export interface Summary { office: Office; seats_up: number; d_total: number; r_total: number;
  o_total: number; d_called: number; r_called: number; o_called: number; uncalled: number;
  majority_line: number|null; est_pct_counted: number|null; mean_pct_reporting: number|null }
export interface MapCounty { fips: string; county_name: string|null; state_po: string|null;
  margin_pp: number|null; pct_reporting: number|null; total_votes: number;
  baseline_margin_pp?: number|null }
/** County updates over the night as parallel columns; row i is one county update. */
export interface Recap { t: number[]; race_id: number[]; fips: string[]; d: number[];
  r: number[]; total: number[]; pct: (number|null)[] }
export interface Candidate { name: string; party_code: "D"|"R"|"I"|"O"; votes: number; pct: number }
export interface Projection { median: number|null; p10: number|null; p90: number|null;
  status: "ok"|"insufficient_data"|"unsupported"|null }
export interface Race { race_id: number; label: string; office: Office; province: string|null;
  district: string|null; candidates: Candidate[]; pct_reporting: number|null;
  winner_party: string|null; margin_pp: number|null; projection: Projection;
  polls_close?: string|null; last_updated?: string|null }
export interface HistoryPoint { as_of: string; median: number|null; p10: number|null;
  p90: number|null; est_pct_counted: number|null }
export interface Check { name: string; status: "pass"|"warn"|"fail"|"error"; detail: string|null }
export interface PipelineInfo { last_ingest_at: string|null; rows_processed: number;
  checks: Check[]; latency: { t: string; p50_ms: number|null }[] }
export interface VotePoint { t: string; name: string; party_code: "D"|"R"|"I"|"O"; votes: number }
