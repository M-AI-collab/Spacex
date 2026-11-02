"""Signals: trend-following score and a walk-forward machine-learning score.

All features at date t use only prices up to and including t.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

import config as C


def _vol(returns: pd.DataFrame, window: int) -> pd.DataFrame:
    return returns.rolling(window).std() * np.sqrt(C.TRADING_DAYS)


def trend_score(prices: pd.DataFrame) -> pd.DataFrame:
    """Share of momentum lookbacks with positive excess return over T-bills, in [0, 1].

    1.0 = uptrend on every horizon, 0.0 = no uptrend (long-only: we hold cash instead of shorting).
    """
    risky = prices[C.RISKY_ASSETS]
    cash = prices[C.CASH_ASSET]
    votes = []
    for lb in C.MOMENTUM_LOOKBACKS:
        excess = risky.pct_change(lb).sub(cash.pct_change(lb), axis=0)
        votes.append((excess > 0).astype(float))
    return sum(votes) / len(votes)


def build_features(prices: pd.DataFrame) -> pd.DataFrame:
    """Long-format feature table indexed by (date, ticker)."""
    risky = prices[C.RISKY_ASSETS]
    rets = risky.pct_change()
    vol63 = _vol(rets, 63)
    vol21 = _vol(rets, 21)
    vol252 = _vol(rets, 252)

    feats = {}
    for lb in C.MOMENTUM_LOOKBACKS:
        # risk-adjusted momentum: return scaled by expected move over the horizon
        feats[f"mom_{lb}"] = risky.pct_change(lb) / (vol63 * np.sqrt(lb / C.TRADING_DAYS))
    sma200 = risky.rolling(200).mean()
    feats["dist_sma200"] = (risky / sma200 - 1) / vol63
    feats["vol_ratio"] = vol21 / vol252
    feats["drawdown_252"] = risky / risky.rolling(252).max() - 1
    feats["xs_rank_126"] = risky.pct_change(126).rank(axis=1, pct=True)
    feats["vol63"] = vol63

    # Market-wide regime features (same value for every asset on a date)
    spy = prices["SPY"]
    spy_rets = spy.pct_change()
    regime = {
        "spy_above_sma200": (spy > spy.rolling(200).mean()).astype(float),
        "spy_vol21": spy_rets.rolling(21).std() * np.sqrt(C.TRADING_DAYS),
        "bond_mom_63": prices["IEF"].pct_change(63),
    }

    frames = []
    for name, df in feats.items():
        frames.append(df.stack().rename(name))
    table = pd.concat(frames, axis=1)
    dates = table.index.get_level_values(0)
    for name, s in regime.items():
        table[name] = s.reindex(dates).values
    table.index.names = ["date", "ticker"]
    return table


def build_labels(prices: pd.DataFrame) -> pd.Series:
    """1 if the asset beats T-bills over the next ML_HORIZON days, else 0. Also returns label end date."""
    h = C.ML_HORIZON
    risky = prices[C.RISKY_ASSETS]
    fwd = risky.shift(-h) / risky - 1
    fwd_cash = prices[C.CASH_ASSET].shift(-h) / prices[C.CASH_ASSET] - 1
    excess = fwd.sub(fwd_cash, axis=0)
    label = (excess > 0).astype(float).where(excess.notna())
    out = label.stack().rename("label")
    out.index.names = ["date", "ticker"]
    return out


def ml_score(prices: pd.DataFrame, rebalance_dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Walk-forward ML conviction in [0, 1] for each rebalance date and asset.

    At each rebalance date the model is re-trained from scratch using only samples whose
    label window has fully ended by that date (no peeking at future returns).
    """
    feats = build_features(prices)
    labels = build_labels(prices)
    data = feats.join(labels, how="left")

    # Weekly training samples (Fridays) to limit overlap between labels.
    dates = data.index.get_level_values("date")
    weekly = dates.dayofweek == 4
    train_pool = data[weekly & (dates >= pd.Timestamp(C.ML_TRAIN_START))].dropna()

    trading_days = prices.index
    feature_cols = [c for c in data.columns if c != "label"]
    out = pd.DataFrame(np.nan, index=rebalance_dates, columns=C.RISKY_ASSETS)

    for d in rebalance_dates:
        pos = trading_days.get_loc(d)
        cutoff = trading_days[max(0, pos - C.ML_HORIZON)]  # last sample whose label is known at d
        train = train_pool[train_pool.index.get_level_values("date") <= cutoff]
        if len(train) < 500:
            continue
        model = HistGradientBoostingClassifier(
            max_depth=3,
            learning_rate=0.05,
            max_iter=200,
            min_samples_leaf=50,
            l2_regularization=1.0,
            random_state=42,
        )
        model.fit(train[feature_cols], train["label"])
        try:
            x = feats.xs(d, level="date")[feature_cols].dropna()
        except KeyError:
            continue
        if x.empty:
            continue
        prob = pd.Series(model.predict_proba(x)[:, 1], index=x.index)
        conviction = ((prob - C.ML_PROB_FLOOR) / (C.ML_PROB_FULL - C.ML_PROB_FLOOR)).clip(0, 1)
        out.loc[d, conviction.index] = conviction
    return out
