"""Projection math (docs/PLAN.md "Projection model"). Pure functions: arrays in, numbers out.

Shares are two-party D shares; margins are 100 * (D - R) / (D + R) in points.
"""

from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import Ridge


@dataclass(frozen=True)
class Params:
    kappa: float = 1.5
    sigma_nu: float = 0.10
    alpha: float = 1.0
    draws: int = 2000
    seed: int = 20261103
    min_informative: int = 8
    informative_pct: float = 20.0
    full_pct: float = 99.0
    shrink_m: float = 10.0
    sigma_floor: float = 0.02
    eta_floor: float = 0.005
    # Within-county vote-type error (mail vs Election Day): SD of how far a partially
    # reported county's counted share can sit from its final share. Prior from real
    # elections, not tuned on the backtest (ADR-006).
    sigma_vt: float = 0.05
    # Display rule (run.py, not the math): publish a projection only once this share of the
    # expected vote is counted. The backtest validated 25-75%; at 10% coverage was 0.66.
    min_pct_counted: float = 25.0


@dataclass
class Fit:
    pred: np.ndarray  # predicted swing per county
    sigma: float  # weighted residual SD (floored)
    n_informative: int
    method: str  # ridge | mean | none
    n_eff: float = 0.0  # Kish effective number of informative counties


@dataclass
class Result:
    status: str  # ok | insufficient_data
    median: float | None
    p10: float | None
    p90: float | None
    p025: float | None
    p975: float | None
    est_expected_votes: float
    est_pct_counted: float  # 0-100
    n_informative: int
    counted_margin: float | None
    method: str


def margin(d: float, r: float) -> float | None:
    return 100.0 * (d - r) / (d + r) if d + r > 0 else None


def expected_turnout(T, V, pct, k0: float, m: float = 10.0, full_pct: float = 99.0):
    """E_c = max(k_hat * T_c, V_c), and E_c = V_c where reporting is complete."""
    T, V, pct = (np.asarray(x, float) for x in (T, V, pct))
    full = pct >= full_pct
    n_full = int(full.sum())
    k_hat = k0
    if n_full and T[full].sum() > 0:
        k_full = V[full].sum() / T[full].sum()
        k_hat = (n_full * k_full + m * k0) / (n_full + m)
    E = np.maximum(k_hat * T, V)
    E[full] = V[full]
    return E, k_hat


def informative_mask(pct, d, r, informative_pct: float = 20.0):
    pct, d, r = (np.asarray(x, float) for x in (pct, d, r))
    return (pct >= informative_pct) & (d + r >= 100)


def fit_swing(s, Z, w, mask, alpha: float, min_informative: int = 8, sigma_floor: float = 0.02):
    """Weighted ridge of swing on features over informative counties; weighted mean swing
    when fewer than min_informative; nothing when there are none."""
    s, w, mask = np.asarray(s, float), np.asarray(w, float), np.asarray(mask, bool)
    n = int(mask.sum())
    C = len(s)
    if n == 0 or w[mask].sum() <= 0:
        return Fit(np.zeros(C), sigma_floor, n, "none")
    ws = w[mask]
    n_eff = float(ws.sum() ** 2 / (ws**2).sum())
    if n < min_informative or Z is None or np.asarray(Z).shape[1] == 0:
        mean = float(np.average(s[mask], weights=ws))
        pred = np.full(C, mean)
        method = "mean"
    else:
        Z = np.asarray(Z, float)
        model = Ridge(alpha=alpha).fit(Z[mask], s[mask], sample_weight=ws)
        pred = model.predict(Z)
        method = "ridge"
    resid = s[mask] - pred[mask]
    sigma = float(np.sqrt(np.average(resid**2, weights=ws)))
    return Fit(pred, max(sigma, sigma_floor), n, method, n_eff)


def project(b, T, V, d, r, pct, Z, k0: float, p: Params, fit: Fit | None = None) -> Result:
    """Final-margin projection with Monte Carlo quantiles. Pass `fit` to reuse a swing fit
    across parameter settings that only change the simulation (kappa, sigma_nu)."""
    b, T, V, d, r, pct = (np.asarray(x, float) for x in (b, T, V, d, r, pct))
    E, _ = expected_turnout(T, V, pct, k0, p.shrink_m, p.full_pct)
    mask = informative_mask(pct, d, r, p.informative_pct)
    tp = d + r
    share = np.divide(d, tp, out=np.zeros_like(d), where=tp > 0)
    w = E * np.minimum(pct / 100.0, 1.0)
    if fit is None:
        fit = fit_swing(share - b, Z, w, mask, p.alpha, p.min_informative, p.sigma_floor)
    counted = margin(d.sum(), r.sum())
    est_e = float(E.sum())
    f = float(V.sum() / est_e) if est_e > 0 else 0.0
    if fit.n_informative == 0:
        return Result(
            "insufficient_data", None, None, None, None, None, est_e, 100 * f, 0, counted, "none"
        )

    theta_state = tp.sum() / V.sum() if V.sum() > 0 else 1.0
    theta = np.divide(tp, V, out=np.full_like(V, theta_state), where=V > 0)
    open_ = pct < p.full_pct
    q = np.clip(b + fit.pred, 0.01, 0.99)

    rng = np.random.default_rng(p.seed)
    n, C = p.draws, len(b)
    # Shared state error: how well the counted counties pin down the swing of the rest,
    # i.e. the standard error of the weighted swing (sigma / sqrt(n_eff)), scaled by kappa
    # for non-random reporting order. It acts only on remaining votes, so it shrinks
    # naturally as counting finishes (no extra (1 - f) factor).
    se = fit.sigma / np.sqrt(max(fit.n_eff, 1.0))
    sigma_eta = p.kappa * se + p.eta_floor
    eta = rng.normal(0.0, sigma_eta, (n, 1)) if sigma_eta > 0 else np.zeros((n, 1))
    eps = rng.normal(0.0, fit.sigma, (n, C)) if fit.sigma > 0 else np.zeros((n, C))
    nu = rng.normal(0.0, p.sigma_nu, (n, 1)) if p.sigma_nu > 0 else np.zeros((n, 1))
    E_draw = np.where(open_, np.maximum(E * np.exp(nu), V), V)
    R2 = np.maximum(E_draw - V, 0.0) * theta
    qd = np.clip(q + eta + eps, 0.01, 0.99)
    D = d.sum() + (R2 * qd).sum(axis=1)
    R = r.sum() + (R2 * (1 - qd)).sum(axis=1)
    # Vote-type error: in partially reported counties the counted votes may lean one way
    # (e.g. mail first) and the rest offset it, so counted two-party votes carry error.
    partial = (pct > 0) & open_
    if p.sigma_vt > 0 and partial.any():
        tp_counted = np.where(partial, tp, 0.0)
        shift = (rng.normal(0.0, p.sigma_vt, (n, C)) * tp_counted).sum(axis=1)
        D, R = D - shift, R + shift
    m = 100.0 * (D - R) / (D + R)
    q025, q10, q50, q90, q975 = np.quantile(m, [0.025, 0.10, 0.50, 0.90, 0.975])
    return Result(
        "ok",
        float(q50),
        float(q10),
        float(q90),
        float(q025),
        float(q975),
        est_e,
        100 * f,
        fit.n_informative,
        counted,
        fit.method,
    )


def standardize(X) -> np.ndarray:
    """Column z-scores within the state; missing values become the mean (0)."""
    X = np.asarray(X, float)
    if X.size == 0:
        return X
    mu = np.nanmean(X, axis=0)
    sd = np.nanstd(X, axis=0)
    Z = (X - mu) / np.where(sd > 0, sd, 1.0)
    return np.nan_to_num(Z, nan=0.0)
