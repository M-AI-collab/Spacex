"""Shared data loading, backtest primitives and statistics for the strategy research."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "adaptive_bot"))
from data import load_all  # noqa: E402  (Binance 4h bars + funding, cached by adaptive_bot)

CAPITAL = 1_000.0
GOAL = 30_000.0
FEE = 0.0005            # per side: taker fee + slippage
MAX_ASSET_LEV = 3.0
MAX_GROSS_LEV = 5.0
VOL_DAYS = 30
START = "2020-01-01"
TRAIN_END = "2023-12-31"
TEST_START = "2024-01-01"


def load_daily():
    """Daily OHLC per asset (dict of DataFrames with columns per asset) and daily funding."""
    bars, funding = load_all()
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    daily = {a: b.resample("1D").agg(agg) for a, b in bars.items()}
    out = {k: pd.DataFrame({a: d[k] for a, d in daily.items()}) for k in agg}
    out["funding"] = funding.resample("1D").sum()
    return out


def vol_scale(close: pd.DataFrame) -> pd.DataFrame:
    vol = close.pct_change().rolling(VOL_DAYS).std() * np.sqrt(365)
    return vol.clip(lower=0.2)


def weights_from_positions(pos: pd.DataFrame, vol: pd.DataFrame, target_vol: float) -> pd.DataFrame:
    """Per-asset vol targeting split across live assets, with leverage caps."""
    live = vol.notna() & pos.notna()
    n = live.sum(axis=1).replace(0, np.nan)
    w = (pos * target_vol / vol).div(n, axis=0).where(live, 0.0).fillna(0.0)
    w = w.clip(-MAX_ASSET_LEV, MAX_ASSET_LEV)
    gross = w.abs().sum(axis=1)
    scale = (MAX_GROSS_LEV / gross).clip(upper=1.0).fillna(1.0)
    return w.mul(scale, axis=0)


def portfolio_returns(w: pd.DataFrame, d: dict) -> pd.Series:
    """Daily net returns. Weights set at close t earn day t+1; fees on turnover; funding; liquidation."""
    close = d["close"]
    prev = close.shift(1)
    r = (close / prev - 1).fillna(0.0)
    held = w.shift(1).fillna(0.0)
    gross = (held * r).sum(axis=1)
    cost = FEE * (w - held).abs().sum(axis=1).shift(1).fillna(0.0)   # trade at close t, booked on t+1
    fund = (held * d["funding"].reindex(w.index).fillna(0.0)).sum(axis=1)
    adverse = np.where(held > 0, d["low"] / prev - 1, d["high"] / prev - 1)
    worst = (held * np.nan_to_num(adverse)).sum(axis=1)
    ret = gross - cost - fund
    ret[worst <= -0.95] = -1.0          # intraday move large enough to liquidate the account
    return ret


def stats(ret: pd.Series) -> dict:
    ret = ret.dropna()
    eq = (1 + ret).cumprod()
    if (ret <= -1).any():
        first = ret.index[ret <= -1][0]
        eq[eq.index >= first] = 0.0
    years = len(ret) / 365.25
    final = eq.iloc[-1]
    sd = ret.std()
    return {
        "Final value": CAPITAL * final,
        "CAGR": final ** (1 / years) - 1 if final > 0 else -1.0,
        "Volatility": sd * np.sqrt(365),
        "Sharpe": ret.mean() / sd * np.sqrt(365) if sd > 0 else 0.0,
        "Max drawdown": (eq / eq.cummax() - 1).min() if final > 0 else -1.0,
        "Liquidated": bool(final <= 0),
    }


def yearly_dollars(ret: pd.Series) -> pd.Series:
    """Value of a fresh $1,000 started on 1 Jan of each year (0 if liquidated)."""
    out = {}
    for y, g in ret.groupby(ret.index.year):
        out[y] = 0.0 if (g <= -1).any() else CAPITAL * (1 + g).prod()
    return pd.Series(out)


def deflated_sharpe(ret: pd.Series, trial_sharpes_daily: np.ndarray) -> float:
    """Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio: probability the true Sharpe > 0
    after correcting for the number of strategies tried and non-normal returns."""
    ret = ret.dropna()
    sr = ret.mean() / ret.std()
    n_trials = len(trial_sharpes_daily)
    var_sr = np.var(trial_sharpes_daily, ddof=1)
    g = 0.5772156649
    sr0 = np.sqrt(var_sr) * ((1 - g) * norm.ppf(1 - 1 / n_trials) + g * norm.ppf(1 - 1 / (n_trials * np.e)))
    t = len(ret)
    sk, ku = skew(ret), kurtosis(ret, fisher=False)
    denom = np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2)
    return float(norm.cdf((sr - sr0) * np.sqrt(t - 1) / denom))
