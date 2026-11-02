"""Survivorship-bias check for the walk-forward winner (XS momentum, 30-day lookback, top 2, long-only).

The main search used 4 coins picked with hindsight (BTC, ETH, SOL, BNB). Here the same strategy runs on
(a) the same universe without SOL, and (b) a wider 10-coin universe including FTT, which collapsed in 2022.
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from common import load_daily, portfolio_returns, stats, vol_scale, weights_from_positions, yearly_dollars
from strategies import xs_momentum

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "adaptive_bot"))
from data import load_funding, load_klines  # noqa: E402

WIDE = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT", "LTCUSDT", "LINKUSDT", "FTTUSDT"]
OUT = Path(__file__).parent / "results"


def daily_for(symbols):
    with ThreadPoolExecutor(8) as ex:
        kl = dict(zip(symbols, ex.map(load_klines, symbols)))
        fu = dict(zip(symbols, ex.map(load_funding, symbols)))
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    d = {k: pd.DataFrame({s: kl[s][k].resample("1D").agg(agg[k]) for s in symbols}) for k in agg}
    d["funding"] = pd.DataFrame({s: fu[s].resample("1D").sum() for s in symbols}).reindex(d["close"].index).fillna(0.0)
    return d


def run(d, tv=0.6):
    pos = xs_momentum(d, lookback=30, top=2)
    return portfolio_returns(weights_from_positions(pos, vol_scale(d["close"]), tv), d).loc["2022-01-01":]


def main():
    base = load_daily()
    no_sol = {k: v.drop(columns="SOLUSDT") for k, v in base.items()}
    wide = daily_for(WIDE)
    rows = {}
    for name, d in [("Original 4 coins (BTC, ETH, SOL, BNB)", base), ("Without SOL (BTC, ETH, BNB)", no_sol),
                    ("Wider 10 coins incl. FTT, DOGE, XRP, ADA, LTC, LINK", wide)]:
        r = run(d)
        s, yd = stats(r), yearly_dollars(r)
        rows[name] = {**{str(y): f"${v:,.0f}" for y, v in yd.items()},
                      "CAGR 2022-26": f"{s['CAGR']:+.1%}", "Sharpe": f"{s['Sharpe']:.2f}", "Max DD": f"{s['Max drawdown']:.1%}"}
    table = pd.DataFrame(rows).T
    md = ["# Survivorship-bias check: XS momentum (30d, top 2) @ 60% vol, Jan 2022 - Oct 2026", "",
          "| Universe | " + " | ".join(table.columns) + " |", "|---" * (len(table.columns) + 1) + "|"]
    md += [f"| {i} | " + " | ".join(row) + " |" for i, row in table.iterrows()]
    (OUT / "ROBUSTNESS.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
