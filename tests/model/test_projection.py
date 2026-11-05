import time

import numpy as np
import pytest

from elex.model.projection import Params, expected_turnout, fit_swing, informative_mask, project

NOISE_OFF = Params(kappa=0, sigma_nu=0, sigma_floor=0, eta_floor=0, sigma_vt=0, draws=200)


def world(n=40, seed=1, swing=0.02, k=0.7):
    """Synthetic state: baseline shares b, 2024 totals T, true final = k*T at share b+swing."""
    rng = np.random.default_rng(seed)
    b = rng.uniform(0.3, 0.7, n)
    T = rng.integers(5_000, 200_000, n).astype(float)
    final = k * T
    share = b + swing
    Z = rng.normal(size=(n, 4))
    return b, T, final, share, Z


def counted(final, share, frac):
    V = final * frac
    d = V * share
    return V, d, V - d, frac * 100


def truth_margin(final, share):
    D, R = (final * share).sum(), (final * (1 - share)).sum()
    return 100 * (D - R) / (D + R)


def test_uniform_swing_recovers_truth_exactly() -> None:
    b, T, final, share, Z = world()
    frac = np.where(np.arange(len(b)) % 3 == 0, 1.0, np.where(np.arange(len(b)) % 3 == 1, 0.5, 0))
    V, d, r, pct = counted(final, share, frac)
    res = project(b, T, V, d, r, pct, Z, k0=0.7, p=NOISE_OFF)
    assert res.status == "ok" and res.method == "ridge"
    assert res.median == pytest.approx(truth_margin(final, share), abs=1e-6)
    assert res.p10 == pytest.approx(res.median, abs=1e-9) == pytest.approx(res.p90, abs=1e-6)


def test_few_informative_counties_use_mean_swing() -> None:
    b, T, final, share, Z = world()
    frac = np.zeros(len(b))
    frac[:5] = 1.0
    V, d, r, pct = counted(final, share, frac)
    res = project(b, T, V, d, r, pct, Z, 0.7, NOISE_OFF)
    assert res.method == "mean" and res.n_informative == 5
    assert res.median == pytest.approx(truth_margin(final, share), abs=1e-6)


def test_no_informative_counties_is_insufficient() -> None:
    b, T, final, share, Z = world()
    V, d, r, pct = counted(final, share, np.zeros(len(b)))
    res = project(b, T, V, d, r, pct, Z, 0.7, Params())
    assert res.status == "insufficient_data" and res.median is None
    assert res.est_pct_counted == 0


def test_everything_counted_equals_counted_margin() -> None:
    b, T, final, share, Z = world()
    V, d, r, pct = counted(final, share, np.ones(len(b)))
    res = project(b, T, V, d, r, pct, Z, 0.7, Params())
    assert res.median == pytest.approx(res.counted_margin, abs=1e-9)
    assert res.p10 == pytest.approx(res.p90, abs=1e-9)
    assert res.est_pct_counted == pytest.approx(100)


def test_more_d_votes_raise_the_median() -> None:
    b, T, final, share, Z = world()
    frac = np.where(np.arange(len(b)) % 2 == 0, 0.6, 0.0)
    lo = project(b, T, *counted(final, share, frac), Z, 0.7, Params())
    hi = project(b, T, *counted(final, share + 0.03, frac), Z, 0.7, Params())
    assert hi.median > lo.median


def test_same_seed_same_output() -> None:
    b, T, final, share, Z = world()
    args = (b, T, *counted(final, share, np.full(len(b), 0.4)), Z, 0.7, Params())
    assert project(*args) == project(*args)


def test_expected_turnout_shrinks_toward_prior() -> None:
    T = np.full(20, 100.0)
    V = np.where(np.arange(20) < 10, 50.0, 0.0)  # 10 full counties at k = 0.5
    pct = np.where(np.arange(20) < 10, 100.0, 0.0)
    E, k_hat = expected_turnout(T, V, pct, k0=0.9, m=10)
    assert k_hat == pytest.approx(0.7)  # (10*0.5 + 10*0.9) / 20
    assert (E[:10] == 50).all() and E[10:] == pytest.approx(70)


def test_informative_mask_rules() -> None:
    m = informative_mask([20, 19, 50], [60, 600, 40], [40, 600, 40])
    assert m.tolist() == [True, False, False]


def test_fit_swing_none_when_empty() -> None:
    f = fit_swing(np.zeros(3), np.zeros((3, 4)), np.ones(3), np.zeros(3, bool), 1.0)
    assert f.method == "none" and f.n_informative == 0


@pytest.mark.slow
def test_254_counties_2000_draws_under_one_second() -> None:
    b, T, final, share, Z = world(n=254)
    args = (b, T, *counted(final, share, np.full(254, 0.5)), Z, 0.7, Params(draws=2000))
    project(*args)  # warm-up (imports, BLAS)
    t0 = time.perf_counter()
    project(*args)
    assert time.perf_counter() - t0 < 1.0


def test_partial_counties_widen_the_band_whole_counties_do_not() -> None:
    b, T, final, share, Z = world()
    whole = np.where(np.arange(len(b)) % 2 == 0, 1.0, 0.0)  # half the counties fully in
    split = np.full(len(b), 0.5)  # same share counted, but every county half in
    p = Params(sigma_vt=0.05)
    a = project(b, T, *counted(final, share, whole), Z, 0.7, p)
    c = project(b, T, *counted(final, share, split), Z, 0.7, p)
    no_vt = project(b, T, *counted(final, share, split), Z, 0.7, Params(sigma_vt=0))
    assert (c.p90 - c.p10) > (no_vt.p90 - no_vt.p10)
    assert (a.p90 - a.p10) == project(
        b, T, *counted(final, share, whole), Z, 0.7, Params(sigma_vt=0)
    ).p90 - project(b, T, *counted(final, share, whole), Z, 0.7, Params(sigma_vt=0)).p10


def test_more_informative_counties_narrow_the_shared_error() -> None:
    b, T, final, share, Z = world(n=200)
    few = np.where(np.arange(200) < 20, 1.0, 0.0)
    many = np.where(np.arange(200) < 100, 1.0, 0.0)
    p = Params(sigma_vt=0)
    w_few = project(b, T, *counted(final, share, few), Z, 0.7, p)
    w_many = project(b, T, *counted(final, share, many), Z, 0.7, p)
    assert (w_many.p90 - w_many.p10) < (w_few.p90 - w_few.p10)
