# ADR-005: Model calibration — needle disabled (counts only)

**Context:** The Chunk 9 backtest (2020 county baseline -> 2024 truth, 45 states, held-out
random seeds 3-4, smallest-first, largest-first and partial reporting) scores the projection
against four gates. Full numbers: `reports/backtest.md`, `reports/backtest_metrics.json`.

**Decision:** Ship counts only (`enabled: false` in `config/model.yaml`), per the plan's rule
"if gates still fail after 2 tuning rounds, set enabled: false".

- Gate 1 (beats the naive count at 50%) **passes** by a wide margin: MAE 0.8 points vs 14.0
  (smallest-first) and 14.5 (largest-first).
- Gate 2 **failed for the ridge model** (MAE 1.09 vs mean swing 1.02 at 50%), so per the plan
  the mean-swing model is the frozen choice (`min_informative: 1000000000`).
- Gate 4 (speed) passes: 254 counties x 2,000 draws in 0.017 s.
- Gate 3 (coverage) **fails** after 2 rounds. The 80% band holds the truth 99-100% of the time
  at 25-50% counted (target 70-90%): too wide for whole-county reporting. Under the partial
  mode (counties report in 25% steps with mail/Election-Day noise) it falls to 0.74 at 75% and
  0.60 at 90%: too narrow. One kappa / sigma_nu cannot fix opposite errors; the model does not
  represent within-county vote-type ordering (the plan's stated limitation).

**Consequences:** The dashboard shows "Counts only" in Key Races; `/api/races` projection
fields stay null. Round 2 of my first tuning attempt widened the bands when they were already
too wide (a bug in my grid choice); the recorded run uses a direction-aware round 2. Next step
if revisited: model within-county reporting order (a separate error term that shrinks with
a county's own % reporting), then re-run the backtest. The real backtest on tonight's archive
(Chunk 11) can confirm or refute this.
