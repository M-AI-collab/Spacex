"""Strategy families for the grid search. Each returns target positions in [-1, 1] per asset per day,
decided at that day's close (applied to the next day's return)."""

import itertools

import numpy as np
import pandas as pd


def _loop(entries_long, entries_short, exits_long, exits_short):
    """Generic per-asset position state machine."""
    out = {}
    for a in entries_long.columns:
        el, es = entries_long[a].to_numpy(), entries_short[a].to_numpy()
        xl, xs = exits_long[a].to_numpy(), exits_short[a].to_numpy()
        p, pos = 0.0, np.zeros(len(el))
        for i in range(len(el)):
            if p == 1 and xl[i]:
                p = 0.0
            elif p == -1 and xs[i]:
                p = 0.0
            if p == 0:
                p = 1.0 if el[i] else (-1.0 if es[i] else 0.0)
            pos[i] = p
        out[a] = pos
    return pd.DataFrame(out, index=entries_long.index)


def tsmom(d, lookback, long_short):
    s = np.sign(d["close"].pct_change(lookback))
    return s if long_short else s.clip(lower=0)


def ma_cross(d, fast, slow, long_short):
    c = d["close"]
    s = np.sign(c.rolling(fast).mean() - c.rolling(slow).mean())
    return s if long_short else s.clip(lower=0)


def donchian(d, n_in, n_out, long_short):
    c = d["close"]
    hi_in, lo_in = d["high"].rolling(n_in).max().shift(1), d["low"].rolling(n_in).min().shift(1)
    hi_out, lo_out = d["high"].rolling(n_out).max().shift(1), d["low"].rolling(n_out).min().shift(1)
    el, es = c > hi_in, (c < lo_in) & long_short
    return _loop(el, es, c < lo_out, c > hi_out)


def rsi_reversion(d, period, lo, hi, long_short):
    c = d["close"]
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    return _loop(rsi < lo, (rsi > hi) & long_short, rsi > 50, rsi < 50)


def bollinger_reversion(d, n, k, long_short):
    c = d["close"]
    m, s = c.rolling(n).mean(), c.rolling(n).std()
    return _loop(c < m - k * s, (c > m + k * s) & long_short, c >= m, c <= m)


def xs_momentum(d, lookback, top, _ls=False):
    """Long the `top` strongest assets by trailing return, only if that return is positive."""
    r = d["close"].pct_change(lookback)
    rank = r.rank(axis=1, ascending=False)
    pos = ((rank <= top) & (r > 0)).astype(float)
    n_live = r.notna().sum(axis=1).replace(0, np.nan)
    return pos.mul(n_live / top, axis=0).where(r.notna())   # concentrate the full budget in the picks


FAMILIES = {
    "TSMOM": (tsmom, [dict(lookback=l) for l in [10, 20, 30, 60, 90, 120, 180]]),
    "MA cross": (ma_cross, [dict(fast=f, slow=s) for f, s in [(5, 20), (10, 30), (10, 50), (20, 50), (20, 100), (50, 200)]]),
    "Donchian": (donchian, [dict(n_in=a, n_out=b) for a, b in [(10, 5), (20, 10), (30, 15), (55, 20), (100, 50)]]),
    "RSI reversion": (rsi_reversion, [dict(period=p, lo=l, hi=h) for p, l, h in [(2, 10, 90), (2, 5, 95), (14, 30, 70), (14, 25, 75)]]),
    "Bollinger reversion": (bollinger_reversion, [dict(n=n, k=k) for n, k in [(10, 2.0), (20, 2.0), (20, 2.5)]]),
    "XS momentum": (xs_momentum, [dict(lookback=l, top=t) for l, t in itertools.product([7, 14, 30, 60, 90], [1, 2])]),
}
TARGET_VOLS = [0.3, 0.6, 1.0]


def all_configs():
    for fam, (fn, grid) in FAMILIES.items():
        modes = [False] if fam == "XS momentum" else [False, True]
        for params, ls, tv in itertools.product(grid, modes, TARGET_VOLS):
            label = ", ".join(f"{k}={v}" for k, v in params.items())
            name = f"{fam} ({label}{', long/short' if ls else ', long-only'}) @ {int(tv * 100)}% vol"
            yield name, fam, fn, params, ls, tv
