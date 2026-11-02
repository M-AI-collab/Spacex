"""Bar-by-bar trade simulator and performance metrics.

Rules (identical for every strategy):
- A signal is evaluated on a bar's CLOSE; the trade is entered at the NEXT bar's OPEN.
- Stop-loss / take-profit are checked intrabar with high/low. If both could be hit in the
  same bar, the STOP is assumed to hit first (conservative). Gaps through a level fill at the open.
- Close-based exits and time stops also fill at the next bar's open.
- One position at a time, 100% of equity, no leverage. Long and short allowed.
- Trading costs are applied afterwards per scenario (fee + slippage per side), so the same trade
  list is evaluated under several cost levels.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Signals:
    long_entry: np.ndarray
    short_entry: np.ndarray
    long_stop: np.ndarray      # absolute price, NaN = none (fixed at the signal bar)
    short_stop: np.ndarray
    long_tp: np.ndarray
    short_tp: np.ndarray
    exit_long: np.ndarray      # close-based exit flags
    exit_short: np.ndarray
    max_hold: int = 0          # bars; 0 = no time stop


def simulate(bars: pd.DataFrame, s: Signals) -> pd.DataFrame:
    o = bars["open"].to_numpy()
    h = bars["high"].to_numpy()
    lo = bars["low"].to_numpy()
    idx = bars.index
    n = len(bars)
    le, se = s.long_entry, s.short_entry
    xl, xs = s.exit_long, s.exit_short

    trades = []
    pos = 0
    entry_px = stop = tp = 0.0
    entry_i = 0
    for k in range(n - 1):
        if pos != 0:
            exit_px = None
            if pos == 1:
                if stop == stop and lo[k] <= stop:          # stop == stop -> not NaN
                    exit_px = min(stop, o[k])
                elif tp == tp and h[k] >= tp:
                    exit_px = max(tp, o[k])
            else:
                if stop == stop and h[k] >= stop:
                    exit_px = max(stop, o[k])
                elif tp == tp and lo[k] <= tp:
                    exit_px = min(tp, o[k])
            if exit_px is None:
                held = k - entry_i + 1
                if (pos == 1 and xl[k]) or (pos == -1 and xs[k]) or (s.max_hold and held >= s.max_hold):
                    exit_px = o[k + 1]
                    exit_i = k + 1
                else:
                    exit_i = None
            else:
                exit_i = k
            if exit_px is not None:
                trades.append((idx[entry_i], idx[exit_i], pos, entry_px, exit_px))
                pos = 0
        if pos == 0 and (le[k] or se[k]):
            pos = 1 if le[k] else -1
            entry_i = k + 1
            entry_px = o[k + 1]
            stop = s.long_stop[k] if pos == 1 else s.short_stop[k]
            tp = s.long_tp[k] if pos == 1 else s.short_tp[k]
    t = pd.DataFrame(trades, columns=["entry_time", "exit_time", "side", "entry", "exit"])
    t["gross"] = t["side"] * (t["exit"] / t["entry"] - 1)
    return t


def evaluate(trades: pd.DataFrame, cost: float, start, end, capital: float) -> dict:
    """Metrics for one cost level (cost = fraction of notional per side)."""
    net = (1 + trades["gross"]) * (1 - cost) ** 2 - 1
    days = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="D", tz="UTC")
    daily_ret = (1 + net).groupby(trades["exit_time"].dt.normalize()).prod().reindex(days, fill_value=1.0) - 1
    equity = capital * (1 + daily_ret).cumprod()
    years = (days[-1] - days[0]).days / 365.25
    final = equity.iloc[-1]
    dd = equity / equity.cummax() - 1
    wins, losses = net[net > 0].sum(), -net[net < 0].sum()
    sd = daily_ret.std()
    return {
        "equity": equity,
        "Final value": final,
        "Total return": final / capital - 1,
        "CAGR": (final / capital) ** (1 / years) - 1 if final > 0 else -1.0,
        "Max drawdown": dd.min(),
        "Sharpe": daily_ret.mean() / sd * np.sqrt(365) if sd > 0 else np.nan,
        "Trades": len(trades),
        "Trades/day": len(trades) / (years * 365.25),
        "Win rate": (net > 0).mean(),
        "Avg trade": net.mean(),
        "Profit factor": wins / losses if losses > 0 else np.nan,
    }


def breakeven_cost(trades: pd.DataFrame) -> float:
    """Cost per side at which compounded profit is exactly zero (NaN if it loses even with zero cost)."""
    mean_log = np.log1p(trades["gross"]).mean()
    return 1 - np.exp(-mean_log / 2) if mean_log > 0 else np.nan
