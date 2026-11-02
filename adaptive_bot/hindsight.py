"""Hindsight upper bound: constant-leverage BTC perp (rebalanced every 4h, funding + fees, liquidation
on intrabar lows) for every 12-month window and leverage 1x-10x. Not a strategy: it shows what was
possible only if you had known the future."""

import numpy as np
import pandas as pd

from data import load_all

GOAL = 30_000.0


def run():
    bars, fund = load_all()
    b = bars["BTCUSDT"].loc["2020-01-01":].dropna()
    f = fund["BTCUSDT"].reindex(b.index).fillna(0)
    levs = np.arange(1, 10.01, 0.5)
    rows = []
    for s in pd.date_range("2020-01-01", "2025-11-01", freq="MS", tz="UTC"):
        w = b[(b.index >= s) & (b.index < s + pd.DateOffset(years=1))]
        c, lo, fw = w["close"].to_numpy(), w["low"].to_numpy(), f.reindex(w.index).to_numpy()
        row = {"start": s.date()}
        for L in levs:
            eq = 1000.0
            for i in range(1, len(c)):
                if 1 + L * (lo[i] / c[i - 1] - 1) <= 0.005 * L:
                    eq = 0.0
                    break
                r = c[i] / c[i - 1] - 1
                eq *= 1 + L * r - L * fw[i] - 0.0005 * L * abs(r)
            row[f"{L:g}x"] = eq
        rows.append(row)
    df = pd.DataFrame(rows).set_index("start")
    df.round(0).to_csv("results/hindsight_btc_leverage.csv")
    best = df.max(axis=1)
    print(f"Start months where SOME leverage reached $30k (hindsight): {(best >= GOAL).sum()}/{len(df)}")
    print(best[best >= GOAL].round(0).to_string())
    for L in ["2x", "3x", "5x"]:
        v = df[L]
        print(f"BTC {L}: reached $30k {(v >= GOAL).mean():.0%}, liquidated {(v == 0).mean():.0%}, median ${v.median():,.0f}")


if __name__ == "__main__":
    run()
