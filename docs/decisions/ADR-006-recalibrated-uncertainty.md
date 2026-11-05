# ADR-006: Recalibrated uncertainty — needle enabled

**Context:** ADR-005 disabled the needle: the 80% band held the truth 99-100% of the time
early (too wide) and only 60% late when counties report in batches (too narrow). Two causes:
the shared state error was sized from the spread between counties (sigma-hat) times kappa,
which overstates how uncertain the average swing is; and the model treated counted votes in
partially reported counties as final, ignoring that early batches (e.g. mail) can lean one way
and the rest of the county offsets them.

**Decision:**
- Shared state error = kappa x the standard error of the weighted swing
  (sigma-hat / sqrt(n_eff), Kish effective number of informative counties) + 0.005. It acts only
  on uncounted votes, so the old extra (1 - f) factor is gone.
- New vote-type term: counted two-party votes in partially reported counties carry
  N(0, sigma_vt) share error. sigma_vt = 0.05 is a prior from real mail vs Election Day gaps,
  not tuned on the backtest (whose partial mode uses 0.03 noise and is held out).
- Tuning grid moved to match (kappa 0.5-6 then a direction-aware round 2; sigma_nu 0-0.06).
  Tuning stays on random-order seeds 0-2; everything below is held out.

**Result (reports/backtest.md):** all four gates pass after round 2. Mean swing is kept
(gate 2: ridge did not beat it). Frozen: kappa 0.1, sigma_nu 0, alpha 0.1 (unused by mean
swing), sigma_vt 0.05. Pooled held-out coverage: 80% band 0.75 / 0.77 / 0.83 and 95% band
0.92 / 0.94 / 0.94 at 25 / 50 / 75% counted. MAE at 50%: 1.07 points vs 7.78 for the raw count.

**Consequences / known limits:**
- Calibration is uneven by reporting order: random and smallest-first are close to target
  (80% coverage 0.82-0.92); largest-first is overconfident (0.56-0.64); partial reporting is
  overconfident early (0.57 at 10%) and well covered late (0.96 at 90%).
- At 10% counted (not gated) pooled 80% coverage is 0.66.
- The median leans about +0.7 points D in this backtest (2020 -> 2024 swing was larger in
  counties counted later).
- Vote-type errors are independent per county; real mail/Election Day skews are correlated
  across a state, so live bands may still be too narrow while big batches are out.
- Display rule (`min_pct_counted: 25`): a projection is published only once 25% of the
  expected vote is counted, the range the backtest validated. Added after the first live
  projection: Kentucky Senate at 1% reporting projected R+6 [R+9, R+3] in a state Trump won
  by ~30, an early-batch skew far outside a band that narrow.
- The needle remains labeled an estimate; `enabled: false` in config/model.yaml is the kill
  switch (read every cycle, no rebuild).
