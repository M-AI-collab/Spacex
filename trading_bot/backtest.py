"""Portfolio construction, backtest engine and performance metrics."""

import numpy as np
import pandas as pd

import config as C


def month_end_dates(index: pd.DatetimeIndex, start, end=None) -> pd.DatetimeIndex:
    s = pd.Series(index, index=index)
    last = s.groupby([index.year, index.month]).max()
    dates = pd.DatetimeIndex(last.values)
    dates = dates[dates >= pd.Timestamp(start) - pd.offsets.MonthEnd(1)]
    if end is not None:
        dates = dates[dates <= pd.Timestamp(end)]
    return dates


def size_portfolio(scores: pd.Series, prices: pd.DataFrame, date) -> pd.Series:
    """Turn asset scores in [0,1] into weights: inverse-vol risk parity, vol target, caps."""
    rets = prices[C.RISKY_ASSETS].pct_change().loc[:date].tail(C.VOL_LOOKBACK)
    vol = rets.std() * np.sqrt(C.TRADING_DAYS)
    inv_vol = 1.0 / vol
    raw = (scores.fillna(0) * inv_vol) / inv_vol.sum()

    if raw.sum() <= 0:
        w = pd.Series(0.0, index=C.RISKY_ASSETS)
    else:
        cov = rets.cov() * C.TRADING_DAYS
        port_vol = float(np.sqrt(raw @ cov @ raw))
        scale = C.TARGET_VOL / port_vol if port_vol > 0 else 0.0
        w = raw * scale
        w = w.clip(upper=C.MAX_ASSET_WEIGHT)
        gross = w.sum()
        if gross > C.MAX_GROSS_EXPOSURE:
            w = w * C.MAX_GROSS_EXPOSURE / gross
    w[C.CASH_ASSET] = 1.0 - w.sum()
    return w


def run_backtest(target_weights: pd.DataFrame, prices: pd.DataFrame, start, end=None) -> pd.DataFrame:
    """Daily simulation. target_weights: rows = signal dates, cols = tickers.

    Trades execute EXECUTION_LAG_DAYS after the signal; weights drift with prices between trades.
    """
    px = prices.loc[:, target_weights.columns]
    rets = px.pct_change().fillna(0.0)
    days = px.index[(px.index >= pd.Timestamp(start))]
    if end is not None:
        days = days[days <= pd.Timestamp(end)]

    # map each signal to its execution day
    exec_map = {}
    for d in target_weights.index:
        pos = px.index.get_loc(d) + C.EXECUTION_LAG_DAYS
        if pos < len(px.index):
            exec_map[px.index[pos]] = target_weights.loc[d]

    w = pd.Series(0.0, index=target_weights.columns)
    w[C.CASH_ASSET] = 1.0
    equity, records = 1.0, []
    for day in days:
        r = rets.loc[day]
        # returns accrue on yesterday's holdings
        gross_ret = float((w * r).sum())
        equity *= 1 + gross_ret
        w = w * (1 + r)
        w = w / w.sum()
        cost = 0.0
        turnover = 0.0
        if day in exec_map:
            new_w = exec_map[day].fillna(0.0)
            turnover = float((new_w - w).abs().sum()) / 2  # one-way
            cost = turnover * 2 * C.COST_PER_TURNOVER
            equity *= 1 - cost
            w = new_w.copy()
        records.append(
            {"date": day, "equity": equity, "turnover": turnover, "cost": cost,
             "risky_exposure": float(w.drop(C.CASH_ASSET, errors="ignore").sum())}
        )
    return pd.DataFrame(records).set_index("date")


def metrics(curve: pd.DataFrame, prices: pd.DataFrame) -> dict:
    eq = curve["equity"]
    daily = eq.pct_change().dropna()
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = eq.iloc[-1] ** (1 / years) - 1
    vol = daily.std() * np.sqrt(C.TRADING_DAYS)
    rf = prices[C.CASH_ASSET].pct_change().reindex(daily.index).fillna(0)
    excess = daily - rf
    sharpe = excess.mean() / daily.std() * np.sqrt(C.TRADING_DAYS)
    downside = daily[daily < 0].std() * np.sqrt(C.TRADING_DAYS)
    sortino = excess.mean() * C.TRADING_DAYS / downside if downside > 0 else np.nan
    dd = eq / eq.cummax() - 1
    max_dd = dd.min()
    monthly = eq.resample("ME").last().pct_change().dropna()
    return {
        "Total return": eq.iloc[-1] - 1,
        "CAGR": cagr,
        "Volatility": vol,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "Max drawdown": max_dd,
        "Calmar (CAGR/MaxDD)": cagr / abs(max_dd) if max_dd < 0 else np.nan,
        "% months positive": (monthly > 0).mean(),
        "Worst month": monthly.min(),
        "Best month": monthly.max(),
        "Avg risky exposure": curve["risky_exposure"].mean(),
        "Annual turnover": curve["turnover"].sum() / years,
    }


def yearly_returns(curve: pd.DataFrame) -> pd.Series:
    eq = curve["equity"]
    first = pd.Series([1.0], index=[eq.index[0] - pd.Timedelta(days=1)])
    year_end = pd.concat([first, eq]).groupby(lambda d: d.year).last()
    return year_end.pct_change().dropna().rename(lambda y: str(y))
