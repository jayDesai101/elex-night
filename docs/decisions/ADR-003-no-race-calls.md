# ADR-003: We never make race calls

**Context:** A projection with an uncertainty band is not a call, and calling races wrongly is a real harm.
**Decision:** Show civicAPI `winner` flags labeled as theirs; projections are labeled estimates with a footer disclaimer.
**Consequences:** Seat cards count only civicAPI-flagged winners plus holdovers; uncalled seats stay gray.
