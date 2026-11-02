"""Backtest four BTC scalping strategies, 2020-01-01 to 2026-10-31, starting with $1,000."""

import time
from pathlib import Path

import numpy as np
import pandas as pd

from data import load_bars, resample
from engine import breakeven_cost, evaluate, simulate
from strategies import bollinger_rsi, ema_crossover, opening_range_breakout, vwap_reversion

CAPITAL = 1_000.0
OUT = Path(__file__).parent / "results"

# Cost per side (fee + slippage) as a fraction of the trade size.
COSTS = {
    "No costs (raw edge)": 0.0,
    "0.02%/side (maker / VIP, optimistic)": 0.0002,
    "0.05%/side (futures taker, typical retail)": 0.0005,
    "0.10%/side (spot taker, standard retail)": 0.0010,
}
REALISTIC = "0.05%/side (futures taker, typical retail)"


def main() -> None:
    t0 = time.time()
    b1 = load_bars()
    b5 = resample(b1, "5min")
    start, end = b1.index[0], b1.index[-1]
    print(f"{len(b1):,} 1-min bars, {start} -> {end} ({time.time() - t0:.0f}s)")

    setups = {
        "VWAP mean reversion (1m)": (vwap_reversion, b1),
        "Bollinger + RSI(2) reversion (5m)": (bollinger_rsi, b5),
        "EMA 9/21 crossover + 1h trend (5m)": (ema_crossover, b5),
        "US opening-range breakout (1m)": (opening_range_breakout, b1),
    }
    trades, results = {}, {}
    for name, (fn, bars) in setups.items():
        t = simulate(bars, fn(bars))
        trades[name] = t
        results[name] = {c: evaluate(t, v, start, end, CAPITAL) for c, v in COSTS.items()}
        print(f"{name}: {len(t):,} trades ({time.time() - t0:.0f}s)")

    days = pd.date_range(start.normalize(), end.normalize(), freq="D", tz="UTC")
    daily_close = b1["close"].resample("D").last().reindex(days).ffill()
    bh = CAPITAL * daily_close / b1["open"].iloc[0]
    bh_years = (days[-1] - days[0]).days / 365.25
    bh_ret = bh.pct_change().dropna()
    bh_stats = {
        "equity": bh, "Final value": bh.iloc[-1], "Total return": bh.iloc[-1] / CAPITAL - 1,
        "CAGR": (bh.iloc[-1] / CAPITAL) ** (1 / bh_years) - 1, "Max drawdown": (bh / bh.cummax() - 1).min(),
        "Sharpe": bh_ret.mean() / bh_ret.std() * np.sqrt(365),
    }

    OUT.mkdir(exist_ok=True)
    write_report(trades, results, bh_stats, start, end)
    plot(results, bh_stats)
    save_csvs(trades, results, bh_stats)
    print((OUT / "RESULTS.md").read_text())


def money(x):
    if x < 0.01:
        return "< $0.01"
    return f"${x:,.2f}" if x < 10 else f"${x:,.0f}"


def pct(x, d=1):
    return f"{x:+.{d}%}" if pd.notna(x) else "n/a"


def write_report(trades, results, bh, start, end) -> None:
    names = list(results)
    L = [
        "# BTC scalping backtest: 4 strategies",
        "",
        f"BTC/USDT 1-minute data (Binance), **{start:%d %b %Y} to {end:%d %b %Y}** · Start capital **$1,000** · "
        "100% of equity per trade, no leverage, long and short · Entry at next bar open · "
        "stop-loss hit first if stop and target touch in the same bar.",
        "",
        f"Benchmark, BTC buy & hold: **{money(bh['Final value'])}** "
        f"(CAGR {pct(bh['CAGR'])}, max drawdown {bh['Max drawdown']:.1%}, Sharpe {bh['Sharpe']:.2f}).",
        "",
        "## Final value of $1,000 under each cost level",
        "",
        "| Strategy | " + " | ".join(COSTS) + " | Break-even cost per side |",
        "|---" * (len(COSTS) + 2) + "|",
    ]
    for n in names:
        be = breakeven_cost(trades[n])
        be_txt = f"{be:.3%}" if pd.notna(be) else "none (loses before costs)"
        L.append(f"| {n} | " + " | ".join(money(results[n][c]["Final value"]) for c in COSTS) + f" | {be_txt} |")

    L += ["", f"## Detail at realistic costs ({REALISTIC})", "",
          "| Strategy | Final value | Total return | CAGR | Max drawdown | Sharpe | Trades | Trades/day | Win rate | Avg trade (net) | Profit factor |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in names:
        r = results[n][REALISTIC]
        L.append(
            f"| {n} | {money(r['Final value'])} | {pct(r['Total return'])} | {pct(r['CAGR'])} | {r['Max drawdown']:.1%} | "
            f"{r['Sharpe']:.2f} | {r['Trades']:,} | {r['Trades/day']:.1f} | {r['Win rate']:.1%} | {pct(r['Avg trade'], 3)} | "
            f"{r['Profit factor']:.2f} |"
        )
    L.append(f"| BTC buy & hold | {money(bh['Final value'])} | {pct(bh['Total return'])} | {pct(bh['CAGR'])} | "
             f"{bh['Max drawdown']:.1%} | {bh['Sharpe']:.2f} | 1 | - | - | - | - |")

    L += ["", "## Raw edge before costs", "",
          "| Strategy | Final value | CAGR | Win rate | Avg trade (gross) | Profit factor | Max drawdown |",
          "|---|---|---|---|---|---|---|"]
    for n in names:
        r = results[n]["No costs (raw edge)"]
        L.append(f"| {n} | {money(r['Final value'])} | {pct(r['CAGR'])} | {r['Win rate']:.1%} | {pct(r['Avg trade'], 3)} | "
                 f"{r['Profit factor']:.2f} | {r['Max drawdown']:.1%} |")

    L += ["", f"## Year-by-year returns at realistic costs ({REALISTIC})", "",
          "| Year | " + " | ".join(names) + " | BTC buy & hold |", "|---" * (len(names) + 2) + "|"]
    yearly = {n: yearly_returns(results[n][REALISTIC]["equity"]) for n in names}
    yearly["bh"] = yearly_returns(bh["equity"])
    for y in yearly["bh"].index:
        label = f"{y} (to {end:%d %b})" if y == end.year else str(y)
        L.append(f"| {label} | " + " | ".join(pct(yearly[k].get(y)) for k in list(names) + ["bh"]) + " |")

    L += ["", "![Equity curves](equity_curves.png)", ""]
    (OUT / "RESULTS.md").write_text("\n".join(L))


def yearly_returns(equity: pd.Series) -> pd.Series:
    ye = equity.groupby(equity.index.year).last()
    prev = ye.shift(1)
    prev.iloc[0] = CAPITAL
    return ye / prev - 1


def plot(results, bh) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
    for ax, cost in zip(axes, ["No costs (raw edge)", REALISTIC]):
        for n, r in results.items():
            ax.plot(r[cost]["equity"].index, r[cost]["equity"], label=n, linewidth=1.4)
        ax.plot(bh["equity"].index, bh["equity"], label="BTC buy & hold", color="black", linewidth=1.0, alpha=0.6)
        ax.axhline(1000, color="grey", linestyle="--", linewidth=0.8)
        ax.set_yscale("log")
        ax.set_title(cost)
        ax.grid(alpha=0.3, which="both")
    axes[0].set_ylabel(r"Portfolio value (USD, log scale, start \$1,000)")
    axes[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("BTC scalping strategies 2020-2026")
    fig.tight_layout()
    fig.savefig(OUT / "equity_curves.png", dpi=120)


def save_csvs(trades, results, bh) -> None:
    rows = []
    for n, by_cost in results.items():
        for c, r in by_cost.items():
            rows.append({"strategy": n, "cost_scenario": c, **{k: v for k, v in r.items() if k != "equity"}})
    pd.DataFrame(rows).to_csv(OUT / "metrics.csv", index=False)
    eq = pd.DataFrame({n: r[REALISTIC]["equity"] for n, r in results.items()})
    eq["BTC buy & hold"] = bh["equity"]
    eq.round(2).to_csv(OUT / "equity_daily_realistic_costs.csv")
    summary = pd.DataFrame({n: {
        "trades": len(t), "long_share": (t["side"] == 1).mean(),
        "median_hold_minutes": ((t["exit_time"] - t["entry_time"]).dt.total_seconds() / 60).median(),
        "avg_gross_trade": t["gross"].mean(),
    } for n, t in trades.items()}).T
    summary.to_csv(OUT / "trade_summary.csv")


if __name__ == "__main__":
    main()
