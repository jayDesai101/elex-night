# ADR-002: Serve versioned Parquet snapshots, not the live DuckDB file

**Context:** DuckDB allows one read-write process or many read-only ones per file, never both, so the API and the archiver would fight over locks.
**Decision:** Each cycle exports gold/model tables to `data/serving/v{ts}/` and atomically swaps a `CURRENT` pointer; the API reads only Parquet.
**Consequences:** No lock contention and instant rollback to the last good version; serving lags ingest by one cycle and disk holds 20 versions.
