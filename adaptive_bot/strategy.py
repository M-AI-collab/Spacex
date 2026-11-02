"""Adaptive Regime Bot: regime detection, three specialist strategies and an online-learning allocator.

Everything at bar t uses information up to bar t's close only. Positions decided at the close of
bar t earn the return of bar t+1.
"""

import numpy as np
import pandas as pd

BARS_PER_DAY = 6                   # 4-hour bars
BARS_PER_YEAR = BARS_PER_DAY * 365
UNIT_VOL = 0.5                     # vol used to normalise specialist returns for the allocator

# Fixed parameters (set before testing)
MOM_DAYS = [7, 30, 90]
EMA_DAYS = 50
VOL_DAYS = 30
VOL_FLOOR = 0.20
DONCHIAN_ENTRY_DAYS, DONCHIAN_EXIT_DAYS = 20, 10
MR_DAYS, MR_ENTRY_Z, MR_EXIT_Z, MR_STOP_Z = 5, 2.0, 0.5, 4.0
ALLOC_LOOKBACK_DAYS = 60
ALLOC_ETA = 1.0
ALLOC_FLOOR = 0.10
STRATEGIES = ["trend", "breakout", "mean_reversion"]


def regimes(close: pd.Series) -> pd.Series:
    """+1 bull trend, -1 bear trend, 0 range (NaN during warm-up)."""
    votes = sum(np.sign(close / close.shift(d * BARS_PER_DAY) - 1) for d in MOM_DAYS)
    ema = close.ewm(span=EMA_DAYS * BARS_PER_DAY, adjust=False).mean()
    reg = pd.Series(0.0, index=close.index)
    reg[(votes > 0) & (close > ema)] = 1.0
    reg[(votes < 0) & (close < ema)] = -1.0
    warm = close.shift(max(MOM_DAYS) * BARS_PER_DAY).isna()
    reg[warm | close.isna()] = np.nan
    return reg


def realised_vol(close: pd.Series) -> pd.Series:
    return (close.pct_change().rolling(VOL_DAYS * BARS_PER_DAY).std() * np.sqrt(BARS_PER_YEAR)).clip(lower=VOL_FLOOR)


def trend_positions(reg: pd.Series) -> pd.Series:
    return reg.fillna(0.0)


def breakout_positions(b: pd.DataFrame) -> pd.Series:
    """Donchian channel: long on a 20-day high, short on a 20-day low, exit on the 10-day opposite extreme."""
    n_in, n_out = DONCHIAN_ENTRY_DAYS * BARS_PER_DAY, DONCHIAN_EXIT_DAYS * BARS_PER_DAY
    hi_in = b["high"].rolling(n_in).max().shift(1).to_numpy()
    lo_in = b["low"].rolling(n_in).min().shift(1).to_numpy()
    hi_out = b["high"].rolling(n_out).max().shift(1).to_numpy()
    lo_out = b["low"].rolling(n_out).min().shift(1).to_numpy()
    c = b["close"].to_numpy()
    pos = np.zeros(len(c))
    p = 0.0
    for i in range(len(c)):
        if np.isnan(c[i]) or np.isnan(hi_in[i]):
            p = 0.0
        elif p == 1 and c[i] < lo_out[i]:
            p = 0.0
        elif p == -1 and c[i] > hi_out[i]:
            p = 0.0
        if p == 0 and not np.isnan(hi_in[i]):
            if c[i] > hi_in[i]:
                p = 1.0
            elif c[i] < lo_in[i]:
                p = -1.0
        pos[i] = p
    return pd.Series(pos, index=b.index)


def mean_reversion_positions(b: pd.DataFrame, reg: pd.Series) -> pd.Series:
    """Fade 2-sigma stretches from the 5-day mean, only while the regime is 'range'."""
    n = MR_DAYS * BARS_PER_DAY
    c = b["close"]
    z = ((c - c.rolling(n).mean()) / c.rolling(n).std()).to_numpy()
    in_range = (reg == 0).to_numpy()
    pos = np.zeros(len(c))
    p = 0.0
    for i in range(len(c)):
        if not in_range[i] or np.isnan(z[i]):
            p = 0.0
        elif p == 1 and (z[i] > -MR_EXIT_Z or z[i] < -MR_STOP_Z):
            p = 0.0
        elif p == -1 and (z[i] < MR_EXIT_Z or z[i] > MR_STOP_Z):
            p = 0.0
        if p == 0 and in_range[i] and not np.isnan(z[i]):
            if -MR_STOP_Z < z[i] < -MR_ENTRY_Z:
                p = 1.0
            elif MR_ENTRY_Z < z[i] < MR_STOP_Z:
                p = -1.0
        pos[i] = p
    return pd.Series(pos, index=b.index)


def allocator_weights(unit_returns: pd.DataFrame) -> pd.DataFrame:
    """Hedge / multiplicative-weights: w ~ exp(eta * trailing Sharpe), 10% floor, updated daily."""
    n = ALLOC_LOOKBACK_DAYS * BARS_PER_DAY
    mu = unit_returns.rolling(n).mean()
    sd = unit_returns.rolling(n).std()
    sharpe = (mu / sd * np.sqrt(BARS_PER_YEAR)).clip(-5, 5)
    raw = np.exp(ALLOC_ETA * sharpe)
    soft = raw.div(raw.sum(axis=1), axis=0)
    k = len(unit_returns.columns)
    w = ALLOC_FLOOR + (1 - ALLOC_FLOOR * k) * soft
    w = w.fillna(1.0 / k)
    daily = pd.Series(w.index.hour == 0, index=w.index)
    return w.where(daily, axis=0).ffill().fillna(1.0 / k)


def build_signals(bars: dict) -> dict:
    """Combined signal in [-1, 1] per asset, plus diagnostics."""
    assets = list(bars)
    idx = next(iter(bars.values())).index
    reg, vol, ret = {}, {}, {}
    spec = {k: {} for k in STRATEGIES}
    for a, b in bars.items():
        reg[a] = regimes(b["close"])
        vol[a] = realised_vol(b["close"])
        ret[a] = b["close"].pct_change()
        live = reg[a].notna()
        spec["trend"][a] = trend_positions(reg[a]).where(live, 0.0)
        spec["breakout"][a] = breakout_positions(b).where(live, 0.0)
        spec["mean_reversion"][a] = mean_reversion_positions(b, reg[a]).where(live, 0.0)
    reg, vol, ret = pd.DataFrame(reg), pd.DataFrame(vol), pd.DataFrame(ret)
    spec = {k: pd.DataFrame(v) for k, v in spec.items()}

    live = reg.notna()
    n_live = live.sum(axis=1).replace(0, np.nan)
    unit = {}
    for k, pos in spec.items():
        contrib = (pos * UNIT_VOL / vol).shift(1) * ret
        unit[k] = contrib.where(live.shift(1, fill_value=False)).sum(axis=1) / n_live.shift(1)
    unit = pd.DataFrame(unit).fillna(0.0)
    weights = allocator_weights(unit)
    signal = sum(spec[k].mul(weights[k], axis=0) for k in STRATEGIES)
    return {"signal": signal.where(live, 0.0), "vol": vol, "regime": reg, "weights": weights,
            "specialists": spec, "unit_returns": unit, "live": live, "assets": assets, "index": idx}
