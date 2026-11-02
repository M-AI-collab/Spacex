"""Leveraged perpetual-futures account simulator with liquidation, funding and fees."""

import numpy as np
import pandas as pd

from strategy import BARS_PER_YEAR

FEE_PER_SIDE = 0.0005          # taker fee + slippage
MAINTENANCE_MARGIN = 0.005     # of gross notional
MAX_ASSET_LEVERAGE = 5.0
MAX_GROSS_LEVERAGE = 10.0
REBALANCE_BAND = 0.10          # trade only if target differs from holding by >10%
DD_STEPS = [(-0.40, 0.25), (-0.25, 0.50)]   # drawdown circuit breaker: (threshold, risk multiplier)


def simulate(sig: dict, bars: dict, funding: pd.DataFrame, target_vol: float,
             start, end, capital: float = 1000.0) -> pd.DataFrame:
    assets = sig["assets"]
    idx = sig["index"]
    mask = (idx >= pd.Timestamp(start, tz="UTC")) & (idx < pd.Timestamp(end, tz="UTC"))
    pos_idx = np.flatnonzero(mask)
    close = pd.DataFrame({a: bars[a]["close"] for a in assets}).ffill().to_numpy()
    high = pd.DataFrame({a: bars[a]["high"] for a in assets}).to_numpy()
    low = pd.DataFrame({a: bars[a]["low"] for a in assets}).to_numpy()
    signal = sig["signal"].to_numpy()
    vol = sig["vol"].to_numpy()
    live = sig["live"].to_numpy()
    fund = funding[assets].to_numpy()

    equity, peak = capital, capital
    notional = np.zeros(len(assets))
    out_eq, out_gross, out_fees, out_fund = [], [], 0.0, 0.0
    liquidated_at = None
    for t in pos_idx:
        prev = close[t - 1]
        # 1) mark-to-market over bar t (check liquidation on worst intrabar prices first)
        if notional.any():
            adverse = np.where(notional > 0, low[t] / prev - 1, high[t] / prev - 1)
            adverse = np.nan_to_num(adverse)
            worst = equity + np.sum(notional * adverse)
            if worst <= MAINTENANCE_MARGIN * np.abs(notional).sum():
                equity = 0.0
                liquidated_at = idx[t]
                out_eq.append(0.0)
                out_gross.append(0.0)
                break
            r = np.nan_to_num(close[t] / prev - 1)
            equity += np.sum(notional * r)
            notional = notional * (1 + r)
            f = np.sum(notional * fund[t])
            equity -= f
            out_fund += f
        if equity <= 0:
            equity, liquidated_at = 0.0, idx[t]
            out_eq.append(0.0)
            out_gross.append(0.0)
            break
        peak = max(peak, equity)
        # 2) new targets at bar close
        dd = equity / peak - 1
        risk = 1.0
        for thr, mult in DD_STEPS:
            if dd < thr:
                risk = mult
                break
        n_live = max(int(live[t].sum()), 1)
        tgt = np.where(live[t], signal[t] * (target_vol / vol[t]) / n_live * risk, 0.0)
        tgt = np.nan_to_num(np.clip(tgt, -MAX_ASSET_LEVERAGE, MAX_ASSET_LEVERAGE)) * equity
        gross = np.abs(tgt).sum()
        if gross > MAX_GROSS_LEVERAGE * equity:
            tgt *= MAX_GROSS_LEVERAGE * equity / gross
        diff = tgt - notional
        trade = np.abs(diff) > REBALANCE_BAND * np.maximum(np.abs(tgt), np.abs(notional))
        fee = FEE_PER_SIDE * np.abs(diff[trade]).sum()
        equity -= fee
        out_fees += fee
        notional = np.where(trade, tgt, notional)
        out_eq.append(equity)
        out_gross.append(np.abs(notional).sum() / equity if equity > 0 else 0.0)

    used = idx[pos_idx[: len(out_eq)]]
    curve = pd.DataFrame({"equity": out_eq, "gross_leverage": out_gross}, index=used)
    curve.attrs.update(liquidated_at=liquidated_at, fees=out_fees, funding=out_fund, capital=capital)
    return curve


def summarize(curve: pd.DataFrame) -> dict:
    cap = curve.attrs["capital"]
    eq = curve["equity"]
    years = max((eq.index[-1] - eq.index[0]).total_seconds() / (365.25 * 86400), 1e-9)
    final = eq.iloc[-1]
    r = eq.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "Final value": final,
        "Return": final / cap - 1,
        "CAGR": (final / cap) ** (1 / years) - 1 if final > 0 else -1.0,
        "Max drawdown": (eq / eq.cummax() - 1).min(),
        "Sharpe": r.mean() / r.std() * np.sqrt(BARS_PER_YEAR) if r.std() > 0 else np.nan,
        "Realised vol": r.std() * np.sqrt(BARS_PER_YEAR),
        "Avg leverage": curve["gross_leverage"].mean(),
        "Max leverage": curve["gross_leverage"].max(),
        "Liquidated": curve.attrs["liquidated_at"] is not None,
        "Fees paid": curve.attrs["fees"],
        "Funding paid": curve.attrs["funding"],
    }
