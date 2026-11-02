"""Run the AI trend + risk-parity bot and benchmarks, then write results.

Usage:
    python run_backtest.py            # use cached prices
    python run_backtest.py --refresh  # re-download prices first
"""

import argparse
from pathlib import Path

import pandas as pd

import config as C
from backtest import metrics, month_end_dates, run_backtest, size_portfolio, yearly_returns
from data import load_prices
from signals import ml_score, trend_score

INITIAL_CAPITAL = 1_000.0
OUT = Path(__file__).parent / "results"
COLUMNS = C.RISKY_ASSETS + [C.CASH_ASSET, C.BENCHMARK_BOND]


def weights_from_scores(scores: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    rows = {d: size_portfolio(scores.loc[d], prices, d) for d in scores.index}
    return pd.DataFrame(rows).T.reindex(columns=COLUMNS).fillna(0.0)


def fixed_weights(dates, mapping: dict) -> pd.DataFrame:
    w = pd.DataFrame(0.0, index=dates, columns=COLUMNS)
    for t, v in mapping.items():
        w[t] = v
    return w


def main(refresh: bool) -> None:
    prices = load_prices(refresh=refresh)
    end = C.BACKTEST_END or prices.index[-1]
    rebal = month_end_dates(prices.index, C.BACKTEST_START, end)
    print(f"Data {prices.index[0].date()} -> {prices.index[-1].date()} | {len(rebal)} rebalances")

    trend = trend_score(prices).reindex(rebal)
    print("Training walk-forward ML model at every rebalance (this takes a minute)...")
    ml = ml_score(prices, rebal).fillna(0.0)
    ai_scores = (1 - C.ML_BLEND) * trend + C.ML_BLEND * ml

    strategies = {
        "AI Trend + Risk Parity bot": weights_from_scores(ai_scores, prices),
        "Trend + Risk Parity (no AI)": weights_from_scores(trend, prices),
        "Static Risk Parity (All Weather-style)": weights_from_scores(
            pd.DataFrame(1.0, index=rebal, columns=C.RISKY_ASSETS), prices),
        "60/40 (SPY/AGG, monthly rebal)": fixed_weights(rebal, {"SPY": 0.6, C.BENCHMARK_BOND: 0.4}),
        "S&P 500 buy & hold (SPY)": fixed_weights(rebal[:1], {"SPY": 1.0}),
    }

    OUT.mkdir(exist_ok=True)
    curves, stats, years = {}, {}, {}
    for name, w in strategies.items():
        curve = run_backtest(w, prices, C.BACKTEST_START, end)
        curves[name] = curve
        stats[name] = metrics(curve, prices)
        years[name] = yearly_returns(curve)

    stats_df = pd.DataFrame(stats)
    years_df = pd.DataFrame(years)
    equity_df = pd.DataFrame({n: c["equity"] * INITIAL_CAPITAL for n, c in curves.items()})
    equity_df.round(2).to_csv(OUT / "equity_curves.csv")
    stats_df.to_csv(OUT / "metrics.csv")
    years_df.to_csv(OUT / "yearly_returns.csv")
    strategies["AI Trend + Risk Parity bot"].round(4).to_csv(OUT / "ai_bot_monthly_weights.csv")

    write_report(stats_df, years_df, equity_df, strategies["AI Trend + Risk Parity bot"], end)
    plot(equity_df, curves)
    print((OUT / "RESULTS.md").read_text())


def pct(x):
    return f"{x:+.1%}" if pd.notna(x) else "n/a"


def write_report(stats, years, equity, ai_weights, end) -> None:
    names = list(stats.columns)
    start_day = equity.index[0].date()
    lines = [
        "# Backtest results: AI Trend + Risk Parity bot",
        "",
        f"Period: **{start_day} to {pd.Timestamp(end).date()}** · Initial capital: **${INITIAL_CAPITAL:,.0f}** · "
        f"Monthly rebalance, next-day execution, {C.COST_PER_TURNOVER * 1e4:.0f} bps cost per trade side, no leverage.",
        "",
        "## Summary",
        "",
        "| Strategy | Final value | Total return | CAGR | Volatility | Sharpe | Sortino | Max drawdown | Calmar |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for n in names:
        s = stats[n]
        lines.append(
            f"| {n} | ${equity[n].iloc[-1]:,.0f} | {pct(s['Total return'])} | {pct(s['CAGR'])} | "
            f"{s['Volatility']:.1%} | {s['Sharpe']:.2f} | {s['Sortino']:.2f} | {s['Max drawdown']:.1%} | "
            f"{s['Calmar (CAGR/MaxDD)']:.2f} |"
        )
    lines += ["", "## Year-by-year returns", "",
              "| Year | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    last_year = str(pd.Timestamp(end).year)
    for y in years.index:
        label = f"{y} (to {pd.Timestamp(end):%d %b})" if y == last_year else y
        lines.append(f"| {label} | " + " | ".join(pct(years.loc[y, n]) for n in names) + " |")

    lines += ["", "## Value of $1,000 at each year end", "",
              "| Date | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    ye = equity.groupby(equity.index.year).tail(1)
    for d, row in ye.iterrows():
        lines.append(f"| {d.date()} | " + " | ".join(f"${row[n]:,.0f}" for n in names) + " |")

    lines += ["", "## Risk and trading statistics", "",
              "| Metric | " + " | ".join(names) + " |", "|---" * (len(names) + 1) + "|"]
    for m in ["% months positive", "Best month", "Worst month", "Avg risky exposure", "Annual turnover"]:
        fmt = (lambda v: f"{v:.0%}") if m in ("% months positive", "Avg risky exposure") else (
            (lambda v: f"{v:.1f}x") if m == "Annual turnover" else pct)
        lines.append(f"| {m} | " + " | ".join(fmt(stats.loc[m, n]) for n in names) + " |")

    latest = ai_weights.iloc[-1]
    latest = latest[latest > 0.001].sort_values(ascending=False)
    lines += ["", f"## Bot's current target allocation (signal of {ai_weights.index[-1].date()})", "",
              "| ETF | Weight |", "|---|---|"]
    lines += [f"| {t} | {v:.1%} |" for t, v in latest.items()]
    lines += ["", "![Equity curves](equity_curve.png)", ""]
    (OUT / "RESULTS.md").write_text("\n".join(lines))


def plot(equity: pd.DataFrame, curves: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True,
                                   gridspec_kw={"height_ratios": [3, 1.3]})
    for n in equity.columns:
        lw = 2.4 if n.startswith("AI") else 1.2
        ax1.plot(equity.index, equity[n], label=n, linewidth=lw)
        dd = curves[n]["equity"] / curves[n]["equity"].cummax() - 1
        ax2.plot(dd.index, dd * 100, linewidth=lw)
    ax1.set_ylabel(r"Portfolio value (USD, start \$1,000)")
    ax1.set_title("AI Trend + Risk Parity bot vs benchmarks")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(alpha=0.3)
    ax2.set_ylabel("Drawdown (%)")
    ax2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "equity_curve.png", dpi=130)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--refresh", action="store_true", help="re-download prices")
    main(p.parse_args().refresh)
