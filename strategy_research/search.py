"""Part 1: honest strategy search.

1) Fixed split: choose strategies on 2020-2023 (train), judge them only on 2024-Oct 2026 (test).
2) Walk-forward: each year from 2022, pick the best strategy using only the years before it, trade it
   for that year, repeat. The chained result is genuinely out-of-sample.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from common import (CAPITAL, GOAL, START, TEST_START, TRAIN_END, deflated_sharpe, load_daily,
                    portfolio_returns, stats, vol_scale, weights_from_positions, yearly_dollars)
from strategies import all_configs, tsmom

OUT = Path(__file__).parent / "results"
TOP_K = 10


def build_returns(d):
    vol = vol_scale(d["close"])
    cache, rets, meta = {}, {}, {}
    for name, fam, fn, params, ls, tv in all_configs():
        key = (fam, tuple(params.items()), ls)
        if key not in cache:
            cache[key] = fn(d, **params, long_short=ls) if fam != "XS momentum" else fn(d, **params)
        rets[name] = portfolio_returns(weights_from_positions(cache[key], vol, tv), d)
        meta[name] = {"family": fam, "target_vol": tv}
    # Pre-registered baseline (fixed from the literature BEFORE running the search):
    # long-only crypto time-series momentum, average of 20/60/120-day signals, 60% vol target.
    base_pos = sum(tsmom(d, l, False) for l in (20, 60, 120)) / 3
    baseline = portfolio_returns(weights_from_positions(base_pos, vol, 0.6), d)
    btc = d["close"]["BTCUSDT"].pct_change().fillna(0.0)
    return pd.DataFrame(rets).loc[START:], pd.DataFrame(meta).T, baseline.loc[START:], btc.loc[START:]


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0.0


def main():
    OUT.mkdir(exist_ok=True)
    d = load_daily()
    R, meta, baseline, btc = build_returns(d)
    n_trials = R.shape[1]
    train, test = R.loc[:TRAIN_END], R.loc[TEST_START:]
    print(f"{n_trials} strategy configurations, {R.index[0].date()} to {R.index[-1].date()}")

    # ---------- fixed split ----------
    rows = []
    for c in R.columns:
        tr, te = stats(train[c]), stats(test[c])
        rows.append({"strategy": c, "family": meta.loc[c, "family"],
                     "train_CAGR": tr["CAGR"], "train_Sharpe": tr["Sharpe"], "train_MaxDD": tr["Max drawdown"],
                     "test_CAGR": te["CAGR"], "test_Sharpe": te["Sharpe"], "test_MaxDD": te["Max drawdown"],
                     "liquidated": tr["Liquidated"] or te["Liquidated"]})
    grid = pd.DataFrame(rows).set_index("strategy")
    grid.round(4).to_csv(OUT / "all_strategies_train_vs_test.csv")
    # Diagnostics on the 60 unique strategies (the 3 risk levels of one strategy share nearly the same Sharpe)
    uniq = grid[grid.index.str.endswith("@ 30% vol")]
    rho = spearmanr(uniq["train_Sharpe"], uniq["test_Sharpe"]).correlation

    picks = {
        "Best train CAGR (naive pick)": R[grid["train_CAGR"].idxmax()],
        "Best train Sharpe": R[grid["train_Sharpe"].idxmax()],
        f"Top-{TOP_K} train-Sharpe ensemble": R[grid["train_Sharpe"].nlargest(TOP_K).index].mean(axis=1),
        "Pre-registered TSMOM baseline": baseline,
        "BTC buy & hold": btc,
    }
    pick_names = {"Best train CAGR (naive pick)": grid["train_CAGR"].idxmax(),
                  "Best train Sharpe": grid["train_Sharpe"].idxmax()}
    trial_sr_daily = (train[uniq.index].mean() / train[uniq.index].std()).to_numpy()
    dsr = deflated_sharpe(train[pick_names["Best train Sharpe"]], trial_sr_daily)

    # ---------- walk-forward ----------
    # Choose the STRATEGY by past Sharpe (among unique strategies), then run it at fixed risk levels.
    levels = {"30% vol": "@ 30% vol", "60% vol": "@ 60% vol", "100% vol": "@ 100% vol"}
    wf_parts = {k: [] for k in levels}
    wf_ens, wf_log = [], []
    for y in range(2022, 2027):
        hist = R.loc[:f"{y - 1}-12-31", uniq.index]
        srs = hist.apply(sharpe)
        best = srs.idxmax()
        top = srs.nlargest(TOP_K).index
        yr = R.loc[f"{y}-01-01":f"{y}-12-31"]
        for k, suffix in levels.items():
            wf_parts[k].append(yr[best.replace("@ 30% vol", suffix)])
        wf_ens.append(yr[[t.replace("@ 30% vol", "@ 60% vol") for t in top]].mean(axis=1))
        wf_log.append({"year": y, "chosen strategy (best Sharpe so far)": best.replace(" @ 30% vol", ""),
                       "its past Sharpe": srs[best]})
    wf = {f"Walk-forward best strategy @ {k}": pd.concat(v) for k, v in wf_parts.items()}
    wf[f"Walk-forward top-{TOP_K} ensemble @ 60% vol"] = pd.concat(wf_ens)
    wf_period = slice("2022-01-01", None)
    wf_bench = {"Pre-registered TSMOM baseline": baseline.loc[wf_period], "BTC buy & hold": btc.loc[wf_period]}

    # ---------- counts against the goal ----------
    yearly_all = pd.DataFrame({c: yearly_dollars(R[c]) for c in R.columns})
    goal_hits = int((yearly_all >= GOAL).to_numpy().sum())
    best_cfg_year = yearly_all.stack().idxmax()

    write_report(grid, rho, picks, pick_names, dsr, n_trials, wf, wf_bench, wf_log, yearly_all, goal_hits, best_cfg_year)
    plot(grid, wf, wf_bench)
    print((OUT / "RESULTS.md").read_text())


def m(x):
    return f"${x:,.0f}"


def write_report(grid, rho, picks, pick_names, dsr, n_trials, wf, wf_bench, wf_log, yearly_all, goal_hits, best_cfg_year):
    L = ["# Part 1: honest strategy search", "",
         f"**{n_trials} strategy configurations** (6 families x parameters x long-only/long-short x 3 risk levels) on "
         "BTC, ETH, SOL, BNB perpetuals, daily bars, 0.05%/side costs, real funding, leverage caps (3x/asset, 5x total), liquidation modelled.", "",
         "## A. Train 2020-2023, test Jan 2024-Oct 2026 (unseen)", "",
         "| Strategy | Train CAGR | Train Sharpe | Test CAGR | Test Sharpe | Test max DD |", "|---|---|---|---|---|---|"]
    for n, r in picks.items():
        tr, te = stats(r.loc[:TRAIN_END]), stats(r.loc[TEST_START:])
        label = f"{n}<br><sub>{pick_names[n]}</sub>" if n in pick_names else n
        L.append(f"| {label} | {tr['CAGR']:+.1%} | {tr['Sharpe']:.2f} | {te['CAGR']:+.1%} | {te['Sharpe']:.2f} | {te['Max drawdown']:.1%} |")
    uniq = grid[grid.index.str.endswith("@ 30% vol")]
    n_uniq = len(uniq)
    deg = (uniq["test_Sharpe"] < uniq["train_Sharpe"]).mean()
    med_tr, med_te = uniq["train_Sharpe"].median(), uniq["test_Sharpe"].median()
    top_decile = uniq[uniq["train_Sharpe"] >= uniq["train_Sharpe"].quantile(0.9)]
    L += ["", "**Overfitting diagnostics**", "",
          f"- Rank correlation between train and test Sharpe across the {n_uniq} unique strategies: **{rho:.2f}** "
          "(1.0 = past ranking perfectly predicts future ranking; 0 = no relation).",
          f"- {deg:.0%} of strategies had a lower Sharpe in the test period. Median Sharpe: {med_tr:.2f} train vs {med_te:.2f} test.",
          f"- Top-10% strategies by train Sharpe: average train Sharpe {top_decile['train_Sharpe'].mean():.2f}, test Sharpe {top_decile['test_Sharpe'].mean():.2f}.",
          f"- **Deflated Sharpe Ratio** of the best-train-Sharpe pick: **{dsr:.0%}** probability its true Sharpe is above zero "
          f"after accounting for {n_uniq} independent strategy trials (Bailey & Lopez de Prado, 2014). Above 95% would count as significant.",
          f"- Liquidated configurations: {int(grid['liquidated'].sum())}.", ""]

    L += ["## B. Walk-forward (each year chosen using only earlier data)", "",
          "| Year | Strategy the bot chose | Its Sharpe up to that point |", "|---|---|---|"]
    for row in wf_log:
        L.append(f"| {row['year']} | {row['chosen strategy (best Sharpe so far)']} | {row['its past Sharpe']:.2f} |")
    L += ["", "Value of a fresh $1,000 each year:", ""]
    series = {**wf, **wf_bench}
    years = sorted(set(series[next(iter(series))].index.year))
    L += ["| Strategy | " + " | ".join(str(y) if y < 2026 else "2026 (to Oct)" for y in years) + " | 2022-26 CAGR | Sharpe | Max DD |",
          "|---" * (len(years) + 4) + "|"]
    for n, r in series.items():
        yd = yearly_dollars(r)
        s = stats(r)
        L.append(f"| {n} | " + " | ".join(m(yd[y]) for y in years) + f" | {s['CAGR']:+.1%} | {s['Sharpe']:.2f} | {s['Max drawdown']:.1%} |")

    L += ["", "## C. Against the $30k goal", "",
          f"- Calendar-year outcomes tested: {yearly_all.size:,} ({n_trials} configs x {yearly_all.shape[0]} years).",
          f"- Outcomes where a fresh $1,000 reached $30,000: **{goal_hits}**.",
          f"- Single best config-year anywhere in the search: **{m(yearly_all.stack().max())}** "
          f"({best_cfg_year[1]}, {best_cfg_year[0]}), found only by looking back.", "",
          "![Train vs test](train_vs_test.png)", ""]
    (OUT / "RESULTS.md").write_text("\n".join(L))


def plot(grid, wf, wf_bench):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(14, 6))
    for fam, g in grid.groupby("family"):
        ax[0].scatter(g["train_Sharpe"], g["test_Sharpe"], s=14, label=fam, alpha=0.75)
    lim = [min(grid["train_Sharpe"].min(), grid["test_Sharpe"].min()) - 0.1,
           max(grid["train_Sharpe"].max(), grid["test_Sharpe"].max()) + 0.1]
    ax[0].plot(lim, lim, color="grey", linestyle="--", linewidth=1, label="test = train")
    ax[0].axhline(0, color="black", linewidth=0.6)
    ax[0].set_xlabel("Sharpe 2020-2023 (train)")
    ax[0].set_ylabel("Sharpe 2024-2026 (test, unseen)")
    ax[0].set_title("Every configuration: past vs future performance")
    ax[0].legend(fontsize=8)
    ax[0].grid(alpha=0.3)
    for n, r in {**wf, **wf_bench}.items():
        ax[1].plot(r.index, CAPITAL * (1 + r).cumprod(), label=n, linewidth=1.4)
    ax[1].axhline(CAPITAL, color="grey", linestyle=":", linewidth=1)
    ax[1].set_yscale("log")
    ax[1].set_title(r"Walk-forward from \$1,000 (Jan 2022 to Oct 2026)")
    ax[1].legend(fontsize=8)
    ax[1].grid(alpha=0.3, which="both")
    fig.tight_layout()
    fig.savefig(OUT / "train_vs_test.png", dpi=110)


if __name__ == "__main__":
    main()
