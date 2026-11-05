"""Simulated-election-night backtest (docs/PLAN.md "Backtest and acceptance gates").

Baseline = 2020 presidential county shares, truth = 2024 presidential county results.
Counties are revealed in several orders; at checkpoints (10..90% of the true state vote)
the model, the naive current count and the mean-swing model are scored against truth.
Uses the same projection.py functions as the live model.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass, replace
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from elex.model.projection import Params, fit_swing, informative_mask, margin, project, standardize
from elex.model.projection import expected_turnout as _expected_turnout
from elex.reference import acs, gazetteer, pres

log = logging.getLogger(__name__)

CHECKPOINTS = (10, 25, 50, 75, 90)
GATE_CPS = (25, 50, 75)
EXCLUDED = {"AK", "CT"}
TUNE_SEEDS = (0, 1, 2)
HELDOUT_SEEDS = (3, 4)
# kappa now scales the standard error of the swing (not the county spread), so its range
# moves up; sigma_nu turnout noise was far too wide at 0.05-0.15 (ADR-006).
GRID_ROUND1 = {
    "kappa": (0.5, 1, 2, 3, 4, 6),
    "sigma_nu": (0.0, 0.03, 0.06),
    "alpha": (0.1, 1, 10),
}
# Round 2 (only if round 1 fails) moves in the direction the held-out coverage missed.
GRID_NARROW = {"kappa": (0.1, 0.25, 0.5, 1), "sigma_nu": (0.0, 0.01, 0.03), "alpha": (0.1, 1, 10)}
GRID_WIDE = {"kappa": (6, 8, 10, 14), "sigma_nu": (0.03, 0.06, 0.10), "alpha": (0.1, 1, 10)}
MEAN_SWING_ONLY = 10**9  # min_informative this high = always the mean-swing model
PARTIAL_NOISE = 0.03
REPORTS = Path("reports")
CONFIG = Path("config/model.yaml")


@dataclass
class State:
    po: str
    b: np.ndarray  # 2020 two-party D share
    T: np.ndarray  # 2020 total votes
    d: np.ndarray  # 2024 D votes (truth)
    r: np.ndarray  # 2024 R votes
    total: np.ndarray  # 2024 total votes
    Z: np.ndarray
    truth: float


def load_states(ref_dir: Path) -> list[State]:
    gaz = gazetteer.read(ref_dir / gazetteer.FILENAME)
    base = pres.county_baseline(
        {y: ref_dir / f"pres_{y}.csv" for y in pres.YEARS}, gazetteer.state_po_by_fips_prefix(gaz)
    )
    feats = acs.county_features(acs.read(ref_dir / f"acs5_{acs.VINTAGE}_county.csv"), gaz)
    df = base.merge(feats, on="county_fips", how="left").dropna(
        subset=["pres20_dem", "pres20_rep", "pres20_total", "pres24_dem", "pres24_rep"]
    )
    df = df[(df.pres20_total > 0) & (df.pres24_total > 0)]
    df["log_income"] = np.log(df["median_hh_income"])
    cols = ["log_density", "pct_bachelors_plus", "log_income", "median_age"]
    states = []
    for po, g in df.groupby("state_po"):
        if po in EXCLUDED or len(g) < 10:
            continue
        d20, r20 = g.pres20_dem.to_numpy(float), g.pres20_rep.to_numpy(float)
        d, r = g.pres24_dem.to_numpy(float), g.pres24_rep.to_numpy(float)
        states.append(
            State(
                po,
                d20 / (d20 + r20),
                g.pres20_total.to_numpy(float),
                d,
                r,
                g.pres24_total.to_numpy(float),
                standardize(g[cols].to_numpy(float)),
                margin(d.sum(), r.sum()),
            )
        )
    return states


def reveal_order(st: State, order: str, seed: int) -> list[tuple[int, int]]:
    """Sequence of (county, step) reveals; full orders use one step of 4/4 per county."""
    n = len(st.b)
    if order == "smallest":
        return [(int(c), 4) for c in np.argsort(st.total, kind="stable")]
    if order == "largest":
        return [(int(c), 4) for c in np.argsort(-st.total, kind="stable")]
    rng = np.random.default_rng(seed)
    if order == "random":
        return [(int(c), 4) for c in rng.permutation(n)]
    # partial: each county reveals in 25% steps, interleaved at random
    events = rng.permutation(np.repeat(np.arange(n), 4))
    seen = np.zeros(n, int)
    out = []
    for c in events:
        seen[c] += 1
        out.append((int(c), int(seen[c])))
    return out


def snapshots(st: State, order: str, seed: int):
    """Yield (checkpoint, V, d, r, pct) when revealed votes first reach each checkpoint."""
    rng = np.random.default_rng(10_000 + seed)
    noise = rng.normal(0, PARTIAL_NOISE, (len(st.b), 4)) if order == "partial" else None
    steps = np.zeros(len(st.b), int)
    total = st.total.sum()
    cps = list(CHECKPOINTS)
    tp = st.d + st.r
    share = st.d / tp
    for c, step in reveal_order(st, order, seed):
        steps[c] = step
        frac = steps / 4
        if frac.dot(st.total) / total * 100 < cps[0]:
            continue
        s = share.copy()
        if noise is not None:
            early = (steps > 0) & (steps < 4)
            s[early] = np.clip(share[early] + noise[early, steps[early] - 1], 0.01, 0.99)
        V = frac * st.total
        dd = frac * tp * s
        while cps and frac.dot(st.total) / total * 100 >= cps[0]:
            yield cps.pop(0), V, dd, frac * tp - dd, frac * 100
        if not cps:
            return


@dataclass
class Case:
    po: str
    order: str
    seed: int
    cp: int
    truth: float
    naive: float | None
    inputs: tuple  # (V, d, r, pct)


def build_cases(states: list[State], runs: list[tuple[str, int]]) -> list[Case]:
    cases = []
    for st in states:
        for order, seed in runs:
            for cp, V, d, r, pct in snapshots(st, order, seed):
                cases.append(
                    Case(st.po, order, seed, cp, st.truth, margin(d.sum(), r.sum()), (V, d, r, pct))
                )
    return cases


def evaluate(cases: list[Case], states: dict[str, State], params: Params, k0: float = 1.0):
    """One row per case: model and mean-swing projections next to truth and naive."""
    rows = []
    mean_p = replace(params, min_informative=10**9)
    for cs in cases:
        st = states[cs.po]
        V, d, r, pct = cs.inputs
        m = project(st.b, st.T, V, d, r, pct, st.Z, k0, params)
        ms = project(st.b, st.T, V, d, r, pct, st.Z, k0, mean_p)
        rows.append(_row(cs, m, ms))
    return pd.DataFrame(rows)


def _row(cs: Case, m, ms) -> dict:
    return {
        "state": cs.po,
        "order": cs.order,
        "seed": cs.seed,
        "cp": cs.cp,
        "truth": cs.truth,
        "naive": cs.naive,
        "model": m.median,
        "p10": m.p10,
        "p90": m.p90,
        "p025": m.p025,
        "p975": m.p975,
        "mean_swing": ms.median,
        "status": m.status,
    }


def tune(cases: list[Case], states: dict[str, State], grid: dict, base: Params, k0: float):
    """Coverage-driven grid search on the tuning cases. Fits are reused across the
    simulation-only knobs (kappa, sigma_nu), so each alpha is fitted once per case."""
    results = []
    combos = list(product(grid["alpha"], grid["kappa"], grid["sigma_nu"]))
    per_combo: dict[tuple, list[dict]] = {c: [] for c in combos}
    for cs in cases:
        st = states[cs.po]
        V, d, r, pct = cs.inputs
        E, _ = _expected_turnout(st.T, V, pct, k0, base.shrink_m, base.full_pct)
        mask = informative_mask(pct, d, r, base.informative_pct)
        tp = d + r
        s = np.divide(d, tp, out=np.zeros_like(d), where=tp > 0) - st.b
        w = E * np.minimum(pct / 100, 1)
        for alpha in grid["alpha"]:
            fit = fit_swing(s, st.Z, w, mask, alpha, base.min_informative, base.sigma_floor)
            for kappa, nu in product(grid["kappa"], grid["sigma_nu"]):
                p = replace(base, alpha=alpha, kappa=kappa, sigma_nu=nu)
                m = project(st.b, st.T, V, d, r, pct, st.Z, k0, p, fit=fit)
                per_combo[(alpha, kappa, nu)].append(
                    {
                        "cp": cs.cp,
                        "truth": cs.truth,
                        "naive": cs.naive,
                        "model": m.median,
                        "p10": m.p10,
                        "p90": m.p90,
                        "p025": m.p025,
                        "p975": m.p975,
                    }
                )
    for (alpha, kappa, nu), rows in per_combo.items():
        df = pd.DataFrame(rows).dropna(subset=["model"])
        at50 = df[df.cp == 50]
        mae, naive_mae = (
            (at50.model - at50.truth).abs().mean(),
            (at50.naive - at50.truth).abs().mean(),
        )
        g = df[df.cp.isin(GATE_CPS)]
        cov80 = ((g.truth >= g.p10) & (g.truth <= g.p90)).mean()
        cov95 = ((g.truth >= g.p025) & (g.truth <= g.p975)).mean()
        results.append(
            {
                "alpha": alpha,
                "kappa": kappa,
                "sigma_nu": nu,
                "mae50": mae,
                "naive_mae50": naive_mae,
                "cov80": cov80,
                "cov95": cov95,
                "beats_naive": bool(mae < naive_mae),
                "score": abs(cov80 - 0.80) + abs(cov95 - 0.95),
            }
        )
    res = pd.DataFrame(results)
    ok = res[res.beats_naive]
    best = (ok if len(ok) else res).sort_values(["score", "mae50"]).iloc[0]
    return res, best


def metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for cp, g in df.groupby("cp"):
        m = g.dropna(subset=["model"])
        big = m[m.truth.abs() > 2]
        out.append(
            {
                "cp": int(cp),
                "n": len(g),
                "n_model": len(m),
                "mae_model": (m.model - m.truth).abs().mean(),
                "mae_naive": (g.naive - g.truth).abs().mean(),
                "mae_mean_swing": (m.mean_swing - m.truth).abs().mean(),
                "bias_model": (m.model - m.truth).mean(),
                "cov80": ((m.truth >= m.p10) & (m.truth <= m.p90)).mean(),
                "cov95": ((m.truth >= m.p025) & (m.truth <= m.p975)).mean(),
                "leader_model": (np.sign(big.model) == np.sign(big.truth)).mean(),
                "leader_naive": (np.sign(big.naive) == np.sign(big.truth)).mean(),
            }
        )
    return pd.DataFrame(out)


def gates(heldout: pd.DataFrame, timing_s: float) -> dict:
    def mae(df, col):
        d = df[df.cp == 50].dropna(subset=["model"])
        return float((d[col] - d.truth).abs().mean())

    g1 = {
        o: {
            "model": mae(heldout[heldout.order == o], "model"),
            "naive": mae(heldout[heldout.order == o], "naive"),
        }
        for o in ("smallest", "largest")
    }
    m = metrics(heldout).set_index("cp")
    g3 = {
        int(cp): {"cov80": float(m.loc[cp, "cov80"]), "cov95": float(m.loc[cp, "cov95"])}
        for cp in GATE_CPS
    }
    return {
        "gate1_beats_naive_at_50": {
            "pass": all(v["model"] < v["naive"] for v in g1.values()),
            "values": g1,
        },
        "gate2_not_worse_than_mean_swing_at_50": {
            "pass": mae(heldout, "model") <= mae(heldout, "mean_swing") + 1e-9,
            "values": {"model": mae(heldout, "model"), "mean_swing": mae(heldout, "mean_swing")},
        },
        "gate3_coverage": {
            "pass": all(
                0.70 <= v["cov80"] <= 0.90 and 0.88 <= v["cov95"] <= 0.99 for v in g3.values()
            ),
            "values": g3,
        },
        "gate4_speed_under_1s": {"pass": timing_s < 1.0, "values": {"seconds": timing_s}},
    }


def timing() -> float:
    rng = np.random.default_rng(0)
    n = 254
    b, T = rng.uniform(0.3, 0.7, n), rng.integers(5_000, 200_000, n).astype(float)
    V = 0.5 * 0.7 * T
    args = (b, T, V, V * b, V * (1 - b), np.full(n, 50.0), rng.normal(size=(n, 4)), 0.7, Params())
    project(*args)
    t0 = time.perf_counter()
    project(*args)
    return time.perf_counter() - t0


def run(ref_dir: Path, out_dir: Path = REPORTS, config: Path = CONFIG) -> dict:
    states = load_states(ref_dir)
    by_po = {s.po: s for s in states}
    log.info("backtest: %d states", len(states))
    base = Params()
    tune_cases = build_cases(states, [("random", s) for s in TUNE_SEEDS])
    held_runs = (
        [("random", s) for s in HELDOUT_SEEDS]
        + [("smallest", 0), ("largest", 0)]
        + [("partial", s) for s in HELDOUT_SEEDS]
    )
    held_cases = build_cases(states, held_runs)
    t = timing()

    rounds = []
    grid = GRID_ROUND1
    for i in (1, 2):
        grid_df, best = tune(tune_cases, by_po, grid, base, 1.0)
        chosen = replace(
            base, alpha=float(best.alpha), kappa=float(best.kappa), sigma_nu=float(best.sigma_nu)
        )
        held = evaluate(held_cases, by_po, chosen, 1.0)
        g = gates(held, t)
        rounds.append(
            {"round": i, "chosen": asdict(chosen), "gates": g, "grid": grid_df, "held": held}
        )
        log.info("round %d: %s", i, {k: v["pass"] for k, v in g.items()})
        if all(v["pass"] for v in g.values()):
            break
        # Plan rule for gate 2: if ridge loses to mean swing, ship the mean-swing model.
        if not g["gate2_not_worse_than_mean_swing_at_50"]["pass"]:
            base = replace(base, min_informative=MEAN_SWING_ONLY)
        cov = metrics(held).set_index("cp").loc[list(GATE_CPS), "cov80"].mean()
        grid = GRID_NARROW if cov > 0.80 else GRID_WIDE
        log.info(
            "round %d held-out cov80 at 25-75%%: %.3f -> %s grid",
            i,
            cov,
            "narrow" if grid is GRID_NARROW else "wide",
        )
    final = rounds[-1]
    chosen = Params(**final["chosen"])
    passed = all(v["pass"] for v in final["gates"].values())
    stress = metrics(evaluate(held_cases, by_po, chosen, 0.9))
    report = {
        "states": len(states),
        "tuning_cases": len(tune_cases),
        "heldout_cases": len(held_cases),
        "rounds": len(rounds),
        "chosen": final["chosen"],
        "passed": passed,
        "gates": final["gates"],
        "heldout_by_checkpoint": metrics(final["held"]).to_dict("records"),
        "heldout_by_order": {
            o: metrics(final["held"][final["held"].order == o]).to_dict("records")
            for o in ("random", "smallest", "largest", "partial")
        },
        "stress_k0_0.9": stress.to_dict("records"),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "backtest_metrics.json").write_text(json.dumps(report, indent=2, default=float))
    final["grid"].to_csv(out_dir / "backtest_grid.csv", index=False)
    _chart(final["held"], out_dir / "backtest_mae.png")
    _markdown(report, out_dir / "backtest.md")
    _freeze(config, chosen, passed)
    return report


def _chart(held: pd.DataFrame, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    m = metrics(held)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(m.cp, m.mae_naive, "o-", label="naive current count")
    ax.plot(m.cp, m.mae_mean_swing, "s-", label="mean swing")
    ax.plot(m.cp, m.mae_model, "^-", label="model (ridge swing)")
    ax.set_xlabel("% of final vote counted")
    ax.set_ylabel("MAE of final margin (points)")
    ax.set_title("Backtest: 2020 baseline -> 2024 truth, held-out runs")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _js(values) -> str:
    return json.dumps(values, default=lambda x: round(float(x), 3))


def _markdown(r: dict, path: Path) -> None:
    lines = [
        "# Backtest",
        "",
        f"Simulated election nights: 2020 presidential county shares as the baseline, 2024 "
        f"results as truth, {r['states']} states (>= 10 counties, AK and CT excluded). "
        f"Tuned on random orders seeds 0-2 ({r['tuning_cases']} cases); evaluated on held-out "
        f"random seeds 3-4, smallest-first, largest-first and partial reporting "
        f"({r['heldout_cases']} cases). Tuning rounds: {r['rounds']}.",
        "",
        f"**Chosen:** kappa = {r['chosen']['kappa']}, sigma_nu = {r['chosen']['sigma_nu']}, "
        f"alpha = {r['chosen']['alpha']}. **All gates passed: {r['passed']}.**",
        "",
        "## Gates (held-out)",
        "",
        "| Gate | Pass | Values |",
        "| --- | --- | --- |",
    ]
    for name, g in r["gates"].items():
        lines.append(f"| {name} | {'yes' if g['pass'] else '**no**'} | `{_js(g['values'])}` |")
    lines += [
        "",
        "## Held-out metrics by checkpoint",
        "",
        "| % counted | MAE model | MAE naive | MAE mean swing | bias | cov80 | cov95 "
        "| leader model | leader naive |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for m in r["heldout_by_checkpoint"]:
        lines.append(
            f"| {m['cp']} | {m['mae_model']:.2f} | {m['mae_naive']:.2f} | "
            f"{m['mae_mean_swing']:.2f} | "
            f"{m['bias_model']:+.2f} | {m['cov80']:.2f} | {m['cov95']:.2f} | "
            f"{m['leader_model']:.2f} | {m['leader_naive']:.2f} |"
        )
    lines += [
        "",
        "![MAE vs % counted](backtest_mae.png)",
        "",
        "Stress run (k0 = 0.9) and per-order metrics are in `backtest_metrics.json`; the "
        "full grid is in `backtest_grid.csv`.",
        "",
        "Known limitation: the order in which vote types are counted inside a county "
        "(mail vs Election Day) is only approximated by the partial-reporting mode.",
    ]
    path.write_text("\n".join(lines) + "\n")


def _freeze(config: Path, p: Params, passed: bool) -> None:
    raw = yaml.safe_load(config.read_text()) if config.exists() else {}
    raw.update({"kappa": p.kappa, "sigma_nu": p.sigma_nu, "alpha": p.alpha, "enabled": passed})
    raw["min_informative"] = p.min_informative  # 10**9 = mean-swing model (gate 2 rule)
    header = (
        "# Projection model settings. kappa, sigma_nu and alpha were tuned by the backtest\n"
        "# (reports/backtest.md, ADR-006) and are frozen here. enabled: false = counts only.\n"
    )
    config.write_text(header + yaml.safe_dump(raw, sort_keys=False))
