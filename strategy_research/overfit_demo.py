"""Part 2: how a 'fake $30k-a-year bot' is made, and what happens on unseen data.

An ExtraTrees model with unlimited depth is trained on 2020-2023 to predict each coin's next-day
direction from 50+ technical features. It memorises the training period. Backtesting on the SAME
period (what many bot sellers do, knowingly or not) shows spectacular profits. On 2024-2026, data
it has never seen, the edge disappears.
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier

from common import CAPITAL, GOAL, TRAIN_END, TEST_START, load_daily, portfolio_returns, stats, yearly_dollars

OUT = Path(__file__).parent / "results"


def features(close: pd.DataFrame) -> pd.DataFrame:
    r = close.pct_change()
    cols = {}
    for a in close.columns:
        for lag in range(1, 11):
            cols[f"{a}_ret_lag{lag}"] = r[a].shift(lag - 1)
        for w in (7, 30, 90):
            cols[f"{a}_mom{w}"] = close[a].pct_change(w)
        cols[f"{a}_vol30"] = r[a].rolling(30).std()
    f = pd.DataFrame(cols)
    f["weekday"] = f.index.dayofweek
    return f


def main():
    d = load_daily()
    close = d["close"].loc["2020-01-01":]
    X = features(d["close"]).loc[close.index]
    nxt = d["close"].pct_change().shift(-1).loc[close.index]
    train_idx = X.index[X.index <= pd.Timestamp(TRAIN_END, tz="UTC")]

    pos = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    for a in close.columns:
        y = (nxt[a] > 0).astype(int)
        ok = X.loc[train_idx].notna().all(axis=1) & nxt.loc[train_idx, a].notna()
        model = ExtraTreesClassifier(n_estimators=300, max_depth=None, min_samples_leaf=1,
                                     bootstrap=False, random_state=0, n_jobs=-1)
        model.fit(X.loc[train_idx][ok], y.loc[train_idx][ok])
        live = X.notna().all(axis=1) & close[a].notna()
        pred = pd.Series(np.nan, index=X.index)
        pred[live] = model.predict(X[live])
        pos[a] = np.where(pred == 1, 1.0, np.where(pred == 0, -1.0, 0.0))

    n_live = (pos != 0).sum(axis=1).replace(0, np.nan)
    w = pos.div(n_live, axis=0).fillna(0.0)              # 1x total exposure, split equally
    ret = portfolio_returns(w, {k: v.loc[close.index] if hasattr(v, "loc") else v for k, v in d.items()})

    yd = yearly_dollars(ret)
    tr, te = stats(ret.loc[:TRAIN_END]), stats(ret.loc[TEST_START:])
    acc = {}
    for name, sl in [("train", slice(None, TRAIN_END)), ("test", slice(TEST_START, None))]:
        p, n = pos.loc[sl], np.sign(nxt.loc[sl])
        m = (p != 0) & n.notna() & (n != 0)
        acc[name] = (p[m] == n[m]).to_numpy().sum() / m.to_numpy().sum()

    L = ["# Part 2: the overfit 'AI bot' (do not trade this)", "",
         "ExtraTrees classifier, unlimited depth, 300 trees, ~57 features per coin, trained on Jan 2020 - Dec 2023 "
         "to predict next-day direction of BTC, ETH, SOL, BNB. Long/short, 1x exposure, 0.05%/side costs + funding.", "",
         "| Period | Direction accuracy | Value of $1,000 per year | CAGR | Sharpe |", "|---|---|---|---|---|",
         f"| **In-sample** 2020-2023 (data it memorised) | {acc['train']:.1%} | "
         + ", ".join(f"{y}: ${yd[y]:,.0f}" for y in yd.index if y <= 2023)
         + f" | {tr['CAGR']:+,.0%} | {tr['Sharpe']:.1f} |",
         f"| **Out-of-sample** 2024-Oct 2026 (unseen) | {acc['test']:.1%} | "
         + ", ".join(f"{y}: ${yd[y]:,.0f}" for y in yd.index if y >= 2024)
         + f" | {te['CAGR']:+.1%} | {te['Sharpe']:.2f} |", "",
         f"In-sample years at or above the $30k goal: **{int((yd[yd.index <= 2023] >= GOAL).sum())} of 4**. "
         f"Out-of-sample years at or above $30k: **{int((yd[yd.index >= 2024] >= GOAL).sum())} of 3**.", "",
         "Why: with unlimited depth the trees memorise every training day's answer, so in-sample 'predictions' are "
         "really look-ups. On new days the same model is close to a coin flip, and fees eat the rest. "
         "This is the same mechanism behind most 'verified backtest' bot adverts.", ""]
    (OUT / "OVERFIT_DEMO.md").write_text("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
