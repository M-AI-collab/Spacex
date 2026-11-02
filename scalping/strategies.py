"""The four scalping strategies. Parameters are standard textbook values, fixed before testing.

Every indicator at bar i uses data up to bar i's close only.
"""

import numpy as np
import pandas as pd

from engine import Signals

NAN = np.nan


def _nan(n):
    return np.full(n, NAN)


def _false(n):
    return np.zeros(n, dtype=bool)


def _atr(b: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = b["close"].shift()
    tr = pd.concat([b["high"] - b["low"], (b["high"] - prev).abs(), (b["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _rsi(close: pd.Series, n: int) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, NAN))


def vwap_reversion(b1: pd.DataFrame) -> Signals:
    """1-minute. Fade 2.5-sigma stretches from the daily (UTC) VWAP; exit back at VWAP.

    Long when the z-score crosses below -2.5, short when it crosses above +2.5.
    Stop at 4 sigma, time stop 60 minutes, no entries in the first hour after the VWAP reset.
    """
    tp_ = (b1["high"] + b1["low"] + b1["close"]) / 3
    day = b1.index.normalize()
    pv = (tp_ * b1["volume"]).groupby(day).cumsum()
    vv = b1["volume"].groupby(day).cumsum().replace(0, NAN)
    vwap = pv / vv
    dev = b1["close"] - vwap
    sd = dev.rolling(60).std()
    z = dev / sd
    minute_of_day = b1.index.hour * 60 + b1.index.minute
    ok = (minute_of_day >= 60) & sd.gt(0)
    le = ((z < -2.5) & (z.shift() >= -2.5) & ok).to_numpy()
    se = ((z > 2.5) & (z.shift() <= 2.5) & ok).to_numpy()
    n = len(b1)
    return Signals(
        long_entry=le, short_entry=se,
        long_stop=(vwap - 4 * sd).to_numpy(), short_stop=(vwap + 4 * sd).to_numpy(),
        long_tp=_nan(n), short_tp=_nan(n),
        exit_long=(b1["close"] >= vwap).to_numpy(), exit_short=(b1["close"] <= vwap).to_numpy(),
        max_hold=60,
    )


def bollinger_rsi(b5: pd.DataFrame) -> Signals:
    """5-minute. Bollinger Bands (20, 2) + RSI(2) extremes.

    Long: close below lower band and RSI(2) < 10. Short: close above upper band and RSI(2) > 90.
    Exit when price returns to the 20-bar mean; stop 1.5 x ATR(14); time stop 2 hours (24 bars).
    """
    c = b5["close"]
    mid = c.rolling(20).mean()
    sd = c.rolling(20).std()
    rsi2 = _rsi(c, 2)
    atr = _atr(b5)
    le = ((c < mid - 2 * sd) & (rsi2 < 10)).to_numpy()
    se = ((c > mid + 2 * sd) & (rsi2 > 90)).to_numpy()
    n = len(b5)
    return Signals(
        long_entry=le, short_entry=se,
        long_stop=(c - 1.5 * atr).to_numpy(), short_stop=(c + 1.5 * atr).to_numpy(),
        long_tp=_nan(n), short_tp=_nan(n),
        exit_long=(c >= mid).to_numpy(), exit_short=(c <= mid).to_numpy(),
        max_hold=24,
    )


def ema_crossover(b5: pd.DataFrame) -> Signals:
    """5-minute. EMA 9/21 crossover, only in the direction of the 1-hour trend (close vs EMA 50).

    Stop 1 x ATR(14), take-profit 2 x ATR(14), exit on the opposite cross, time stop 4 hours.
    The 1-hour filter uses only fully completed hourly bars.
    """
    c = b5["close"]
    fast, slow = c.ewm(span=9, adjust=False).mean(), c.ewm(span=21, adjust=False).mean()
    up_cross = (fast > slow) & (fast.shift() <= slow.shift())
    dn_cross = (fast < slow) & (fast.shift() >= slow.shift())
    hourly = c.resample("1h", label="left", closed="left").last().dropna()
    trend_up_h = (hourly > hourly.ewm(span=50, adjust=False).mean()).shift(1)  # completed hours only
    trend_up = trend_up_h.reindex(b5.index, method="ffill").fillna(False).astype(bool)
    atr = _atr(b5)
    le = (up_cross & trend_up).to_numpy()
    se = (dn_cross & ~trend_up).to_numpy()
    return Signals(
        long_entry=le, short_entry=se,
        long_stop=(c - atr).to_numpy(), short_stop=(c + atr).to_numpy(),
        long_tp=(c + 2 * atr).to_numpy(), short_tp=(c - 2 * atr).to_numpy(),
        exit_long=dn_cross.to_numpy(), exit_short=up_cross.to_numpy(),
        max_hold=48,
    )


def opening_range_breakout(b1: pd.DataFrame) -> Signals:
    """1-minute. US-session opening range breakout (New York time, weekdays).

    Opening range = high/low of 09:30-09:59 ET. From 10:00 to 11:59 ET, the first 1-minute close
    outside the range triggers one trade per day in that direction. Stop at the opposite side of
    the range; exit at the 16:00 ET close.
    """
    ny = b1.index.tz_convert("America/New_York")
    mins = ny.hour * 60 + ny.minute
    date = ny.date
    weekday = ny.dayofweek < 5
    in_or = (mins >= 570) & (mins < 600) & weekday
    g = pd.Series(date, index=b1.index)
    orh = b1["high"].where(in_or).groupby(g.values).transform("max")
    orl = b1["low"].where(in_or).groupby(g.values).transform("min")
    window = (mins >= 600) & (mins < 720) & weekday
    c = b1["close"]
    brk_up = (c > orh) & window
    brk_dn = (c < orl) & window
    any_brk = brk_up | brk_dn
    first = any_brk & (any_brk.astype(int).groupby(g.values).cumsum() == 1)
    n = len(b1)
    session_end = pd.Series(mins == 959, index=b1.index).to_numpy()  # 15:59 bar -> exit at 16:00 open
    return Signals(
        long_entry=(first & brk_up).to_numpy(), short_entry=(first & brk_dn).to_numpy(),
        long_stop=orl.to_numpy(), short_stop=orh.to_numpy(),
        long_tp=_nan(n), short_tp=_nan(n),
        exit_long=session_end, exit_short=session_end,
        max_hold=0,
    )
