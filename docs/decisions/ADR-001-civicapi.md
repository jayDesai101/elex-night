# ADR-001: civicAPI v2 as the live results source

**Context:** We need free, keyless, county-level live results for the 2026 midterms; AP and similar feeds cost money.
**Decision:** Poll civicAPI v2 (`region_results` gives county detail; `/history` is a server-side backup) with our own rate budget.
**Consequences:** No FIPS codes or region candidate IDs, so we maintain a crosswalk; attribution "Data: civicAPI" is required in the footer.
