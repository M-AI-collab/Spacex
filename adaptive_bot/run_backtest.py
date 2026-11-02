"""Backtest the Adaptive Regime Bot: full period, calendar years and rolling 12-month windows."""

import time
from pathlib import Path

import numpy as np
import pandas as pd

from data import load_all
from simulator import simulate, summarize
from strategy import build_signals

CAPITAL = 1_000.0
GOAL = 30_000.0
OUT = Path(__file__).parent / "results"
# Risk budget = target volatility of a FULL-conviction portfolio. Because the specialists often
# disagree (average signal strength ~0.5) and the drawdown breaker cuts risk, realised volatility is
# much lower than the budget; the report shows the realised figures.
RISK_LEVELS = {
    "L1 Conservative (budget 30%)": 0.30,
    "L2 Moderate (budget 60%)": 0.60,
    "L3 Aggressive (budget 100%)": 1.00,
    "L4 Very aggressive (budget 200%)": 2.00,
    "L5 Extreme (budget 300%)": 3.00,
    "L6 Maximum (budget 500%)": 5.00,
}
FULL_START, FULL_END = "2020-01-01", "2026-11-01"


def btc_hold(bars, start, end):
    c = bars["BTCUSDT"]["close"]
    c = c[(c.index >= pd.Timestamp(start, tz="UTC")) & (c.index < pd.Timestamp(end, tz="UTC"))].dropna()
    return CAPITAL * c.iloc[-1] / c.iloc[0], (c / c.cummax() - 1).min()


def money(x):
    return f"${x:,.0f}" if x >= 1 else f"${x:,.2f}"


def main():
    t0 = time.time()
    bars, funding = load_all()
    sig = build_signals(bars)
    print(f"signals ready ({time.time() - t0:.0f}s)")
    OUT.mkdir(exist_ok=True)

    # 1) Full period
    full = {name: simulate(sig, bars, funding, tv, FULL_START, FULL_END, CAPITAL) for name, tv in RISK_LEVELS.items()}
    full_stats = {n: summarize(c) for n, c in full.items()}
    bh_full, bh_full_dd = btc_hold(bars, FULL_START, FULL_END)

    # 2) Calendar years (fresh $1,000 each year)
    years = list(range(2020, 2027))
    cal = {}
    for y in years:
        s, e = f"{y}-01-01", f"{y + 1}-01-01" if y < 2026 else FULL_END
        cal[y] = {n: summarize(simulate(sig, bars, funding, tv, s, e, CAPITAL)) for n, tv in RISK_LEVELS.items()}
        cal[y]["BTC buy & hold"] = btc_hold(bars, s, e)[0]

    # 3) Rolling 12-month windows starting every month
    starts = pd.date_range("2020-01-01", "2025-11-01", freq="MS")
    roll_rows = []
    for s in starts:
        e = s + pd.DateOffset(years=1)
        row = {"start": s.date()}
        for n, tv in RISK_LEVELS.items():
            st = summarize(simulate(sig, bars, funding, tv, s, e, CAPITAL))
            row[n] = st["Final value"]
            row[n + " liquidated"] = st["Liquidated"]
        row["BTC buy & hold"] = btc_hold(bars, s, e)[0]
        roll_rows.append(row)
    roll = pd.DataFrame(roll_rows)
    print(f"backtests done ({time.time() - t0:.0f}s)")

    roll.to_csv(OUT / "rolling_12m_windows.csv", index=False)
    pd.DataFrame(full_stats).T.to_csv(OUT / "full_period_metrics.csv")
    pd.DataFrame({n: c["equity"] for n, c in full.items()}).resample("D").last().round(2).to_csv(OUT / "equity_full_period.csv")
    sig["weights"].resample("W").last().round(3).to_csv(OUT / "allocator_weights_weekly.csv")

    write_report(full_stats, bh_full, bh_full_dd, cal, years, roll, sig)
    plot(full, roll, sig, bars)
    print((OUT / "RESULTS.md").read_text())


def write_report(full_stats, bh_full, bh_full_dd, cal, years, roll, sig):
    names = list(RISK_LEVELS)
    L = ["# Adaptive Regime Bot: backtest results", "",
         "BTC, ETH, SOL, BNB perpetuals · 4-hour bars · $1,000 start · 0.05%/side costs + actual Binance funding · "
         "liquidation modelled · **goal: $30,000 in 12 months**", "",
         "## 1. Rolling 12-month windows: how often was the $30k goal reached?", "",
         f"{len(roll)} windows, one starting on the 1st of every month from {roll['start'].iloc[0]} to {roll['start'].iloc[-1]}, "
         "each starting with a fresh $1,000.", "",
         "| Risk level | Realised vol (full period) | Reached $30k | Ended above $1,000 | Lost > 50% | Lost > 90% or liquidated | Median end value | Best window | Worst window |",
         "|---|---|---|---|---|---|---|---|---|"]
    for n in names + ["BTC buy & hold"]:
        v = roll[n]
        liq = roll.get(n + " liquidated", pd.Series(False, index=roll.index))
        ruin = ((v < 0.1 * CAPITAL) | liq).mean()
        best_i, worst_i = v.idxmax(), v.idxmin()
        rv = f"{full_stats[n]['Realised vol']:.0%}" if n in full_stats else "~60%"
        L.append(f"| {n} | {rv} | **{(v >= GOAL).mean():.0%}** ({int((v >= GOAL).sum())}/{len(v)}) | {(v > CAPITAL).mean():.0%} | "
                 f"{(v < 0.5 * CAPITAL).mean():.0%} | {ruin:.0%} | {money(v.median())} | "
                 f"{money(v.max())} (from {roll['start'][best_i]}) | {money(v.min())} (from {roll['start'][worst_i]}) |")

    L += ["", "## 2. Calendar years (fresh $1,000 every 1 January)", "",
          "| Year | " + " | ".join(names) + " | BTC buy & hold |", "|---" * (len(names) + 2) + "|"]
    for y in years:
        cells = []
        for n in names:
            s = cal[y][n]
            tag = " (liquidated)" if s["Liquidated"] else (" ✅ goal" if s["Final value"] >= GOAL else "")
            cells.append(money(s["Final value"]) + tag)
        label = f"{y} (Jan-Oct)" if y == 2026 else str(y)
        L.append(f"| {label} | " + " | ".join(cells) + f" | {money(cal[y]['BTC buy & hold'])} |")

    L += ["", "## 3. Full period, 1 Jan 2020 to 31 Oct 2026 (one $1,000 account, never topped up)", "",
          "| Risk level | Final value | CAGR | Realised vol | Max drawdown | Sharpe | Avg leverage | Max leverage | Liquidated | Fees paid | Funding paid |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in names:
        s = full_stats[n]
        L.append(f"| {n} | {money(s['Final value'])} | {s['CAGR']:+.1%} | {s['Realised vol']:.0%} | {s['Max drawdown']:.1%} | {s['Sharpe']:.2f} | "
                 f"{s['Avg leverage']:.2f}x | {s['Max leverage']:.1f}x | {'yes' if s['Liquidated'] else 'no'} | {money(s['Fees paid'])} | {money(s['Funding paid'])} |")
    L.append(f"| BTC buy & hold | {money(bh_full)} | {(bh_full / CAPITAL) ** (1 / 6.83) - 1:+.1%} | ~60% | {bh_full_dd:.1%} | - | 1.00x | 1.0x | no | - | - |")

    reg = sig["regime"].loc[FULL_START:]
    w = sig["weights"].loc[FULL_START:]
    L += ["", "## 4. How the bot adapted", "",
          "Share of time each asset spent in each regime (2020-2026):", "",
          "| Asset | Bull trend | Range | Bear trend |", "|---|---|---|---|"]
    for a in reg.columns:
        r = reg[a].dropna()
        L.append(f"| {a} | {(r == 1).mean():.0%} | {(r == 0).mean():.0%} | {(r == -1).mean():.0%} |")
    L += ["", "Average AI-allocator weight on each specialist, by year:", "",
          "| Year | Trend | Breakout | Mean reversion |", "|---|---|---|---|"]
    for y, g in w.groupby(w.index.year):
        L.append(f"| {y} | {g['trend'].mean():.0%} | {g['breakout'].mean():.0%} | {g['mean_reversion'].mean():.0%} |")
    L += ["", "![Results](results.png)", ""]
    (OUT / "RESULTS.md").write_text("\n".join(L))


def plot(full, roll, sig, bars):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(3, 1, figsize=(12, 13))
    for n, c in full.items():
        ax[0].plot(c.index, c["equity"].clip(lower=0.01), label=n, linewidth=1.3)
    btc = bars["BTCUSDT"]["close"].loc[FULL_START:].dropna()
    ax[0].plot(btc.index, CAPITAL * btc / btc.iloc[0], color="black", alpha=0.5, linewidth=1, label="BTC buy & hold")
    ax[0].axhline(GOAL, color="green", linestyle="--", linewidth=1, label="$30k goal")
    ax[0].set_yscale("log")
    ax[0].set_title(r"Full period from \$1,000 (log scale)")
    ax[0].legend(fontsize=8, loc="upper left")
    ax[0].grid(alpha=0.3, which="both")

    x = pd.to_datetime(roll["start"])
    for n in list(RISK_LEVELS) + ["BTC buy & hold"]:
        ax[1].plot(x, roll[n].clip(lower=1), marker="o", markersize=3, linewidth=1, label=n,
                   color="black" if n.startswith("BTC") else None, alpha=0.6 if n.startswith("BTC") else 1)
    ax[1].axhline(GOAL, color="green", linestyle="--", linewidth=1)
    ax[1].axhline(CAPITAL, color="grey", linestyle=":", linewidth=1)
    ax[1].set_yscale("log")
    ax[1].set_title(r"Value after 12 months of \$1,000, by start month (green = \$30k goal)")
    ax[1].grid(alpha=0.3, which="both")

    w = sig["weights"].loc[FULL_START:].resample("W").last()
    ax[2].stackplot(w.index, w["trend"], w["breakout"], w["mean_reversion"],
                    labels=["Trend", "Breakout", "Mean reversion"], alpha=0.8)
    ax[2].set_title("AI allocator: capital share given to each specialist")
    ax[2].legend(fontsize=8, loc="upper left")
    ax[2].set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(OUT / "results.png", dpi=110)


if __name__ == "__main__":
    main()
