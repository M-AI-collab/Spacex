"""Pro-style US opening-range breakout on BTC 1-minute bars, 2020-01-01 to 2026-10-31.

Built in steps so each improvement's contribution is visible. All rules were fixed BEFORE running:

  V0 Original     Opening range 09:30-09:59 ET. First 1m close outside it between 10:00 and 11:59 ET
                  triggers one trade per weekday, entered at the next bar's open. Stop at the opposite
                  side of the range, exit at the 16:00 ET close. Position = 100% of equity.
  V1 + risk sizing    Risk 1% of equity per trade: size = 1% equity / stop distance, capped at 5x leverage.
  V2 + partials       Take half off at +1R, move the stop to breakeven, run the rest to the close.
  V3 + filters        Only trade in the direction of the daily trend (previous session close vs its
                      20-session EMA) and only if the breakout bar's volume >= 1.5x the opening range's
                      average 1-minute volume.

Fills: stop and target checked on 1m high/low, stop assumed first if both touched in one bar, gaps
through a level fill at the bar open. Costs are charged per side on the notional traded.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from data import load_bars

CAPITAL = 1_000.0
OUT = Path(__file__).parent / "results"
COSTS = {"0% (raw edge)": 0.0, "0.01% (pro / maker rebates)": 0.0001,
         "0.02% (pro futures)": 0.0002, "0.05% (retail)": 0.0005}
VARIANTS = {
    "V0 Original ORB": dict(risk_sizing=False, partials=False, filters=False),
    "V1 + 1% risk sizing": dict(risk_sizing=True, partials=False, filters=False),
    "V2 + partial profit & breakeven stop": dict(risk_sizing=True, partials=True, filters=False),
    "V3 + trend & volume filters (full pro)": dict(risk_sizing=True, partials=True, filters=True),
}
RISK_PER_TRADE = 0.01
MAX_LEVERAGE = 5.0
VOLUME_MULT = 1.5
TREND_EMA = 20


def sessions(b1: pd.DataFrame):
    """Yield (date, arrays) for each weekday New York session 09:30-15:59."""
    ny = b1.index.tz_convert("America/New_York")
    mins = ny.hour * 60 + ny.minute
    keep = (mins >= 570) & (mins < 960) & (ny.dayofweek < 5)
    sub = b1[keep]
    m = mins[keep]
    dates = ny[keep].date
    o, h, lo, c, v = (sub[k].to_numpy() for k in ["open", "high", "low", "close", "volume"])
    bounds = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1], True])
    for s, e in zip(bounds[:-1], bounds[1:]):
        yield dates[s], m[s:e], o[s:e], h[s:e], lo[s:e], c[s:e], v[s:e]


def simulate_day(m, o, h, lo, c, v, allow_long, allow_short, risk_sizing, partials, filters):
    """Return (side, trade gross legs as list of (fraction_of_position, exit_price), entry, notional_mult, R)
    or None if no trade."""
    in_or = m < 600
    if in_or.sum() < 25 or (m >= 600).sum() == 0:
        return None
    orh, orl = h[in_or].max(), lo[in_or].min()
    or_vol = v[in_or].mean()
    win = np.flatnonzero((m >= 600) & (m < 720))
    brk = None
    for i in win:
        if c[i] > orh:
            brk = (i, 1)
            break
        if c[i] < orl:
            brk = (i, -1)
            break
    if brk is None or brk[0] + 1 >= len(c):
        return None
    i, side = brk
    if filters:
        if (side == 1 and not allow_long) or (side == -1 and not allow_short):
            return None
        if v[i] < VOLUME_MULT * or_vol:
            return None
    j = i + 1
    entry = o[j]
    stop = orl if side == 1 else orh
    risk = (entry - stop) * side
    if risk <= 0:
        return None
    lev = min(RISK_PER_TRADE / (risk / entry), MAX_LEVERAGE) if risk_sizing else 1.0
    target = entry + side * risk
    legs, remaining, cur_stop, took_partial = [], 1.0, stop, False
    for k in range(j, len(c)):
        hit_stop = lo[k] <= cur_stop if side == 1 else h[k] >= cur_stop
        if hit_stop:
            px = min(cur_stop, o[k]) if side == 1 else max(cur_stop, o[k])
            legs.append((remaining, px))
            remaining = 0.0
            break
        if partials and not took_partial:
            hit_tgt = h[k] >= target if side == 1 else lo[k] <= target
            if hit_tgt:
                px = max(target, o[k]) if side == 1 else min(target, o[k])
                legs.append((0.5, px))
                remaining, cur_stop, took_partial = 0.5, entry, True
    if remaining > 0:
        legs.append((remaining, c[-1]))
    return side, legs, entry, lev, risk


def run():
    b1 = load_bars()
    days = list(sessions(b1))
    # daily trend filter: previous session close vs EMA of session closes (known before today's open)
    closes = pd.Series([d[5][-1] for d in days], index=[d[0] for d in days])
    ema = closes.ewm(span=TREND_EMA, adjust=False).mean()
    up = (closes > ema).shift(1).fillna(False).to_numpy()
    down = (closes < ema).shift(1).fillna(False).to_numpy()

    trades = {}
    for vname, cfg in VARIANTS.items():
        rows = []
        for n, (date, m, o, h, lo, c, v) in enumerate(days):
            res = simulate_day(m, o, h, lo, c, v, up[n], down[n], **cfg)
            if res is None:
                continue
            side, legs, entry, lev, risk = res
            gross = sum(frac * side * (px / entry - 1) for frac, px in legs)
            turnover = 1.0 + sum(frac * px / entry for frac, px in legs)    # entry + exits, per unit notional
            rows.append({"date": pd.Timestamp(date), "side": side, "lev": lev, "gross": gross,
                         "turnover": turnover, "R": gross / (risk / entry)})
        trades[vname] = pd.DataFrame(rows).set_index("date")
    return trades, closes.index


def equity_for(t: pd.DataFrame, cost: float, all_days) -> pd.Series:
    net = t["lev"] * (t["gross"] - cost * t["turnover"])
    daily = net.reindex(pd.DatetimeIndex(all_days), fill_value=0.0)
    return CAPITAL * (1 + daily).cumprod()


def metrics(eq: pd.Series, t: pd.DataFrame, cost: float) -> dict:
    r = eq.pct_change().fillna(eq.iloc[0] / CAPITAL - 1)
    years = (eq.index[-1] - eq.index[0]).days / 365.25
    net = t["lev"] * (t["gross"] - cost * t["turnover"])
    wins, losses = net[net > 0].sum(), -net[net < 0].sum()
    return {
        "Final value": eq.iloc[-1],
        "CAGR": (eq.iloc[-1] / CAPITAL) ** (1 / years) - 1,
        "Max drawdown": (eq / eq.cummax() - 1).min(),
        "Sharpe": r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else np.nan,
        "Trades": len(t),
        "Win rate": (net > 0).mean(),
        "Profit factor": wins / losses if losses > 0 else np.nan,
        "Avg leverage": t["lev"].mean(),
    }


def main():
    OUT.mkdir(exist_ok=True)
    trades, all_days = run()
    L = ["# Pro-style opening-range breakout: BTC 1-minute data, Jan 2020 to Oct 2026", "",
         "Start capital $1,000. One trade per weekday max. Rules fixed before testing (see `pro_orb.py`). "
         "Cost = fee + slippage per side, on the notional traded.", "",
         "## Final value of $1,000, by variant and cost level", "",
         "| Variant | Trades | " + " | ".join(COSTS) + " |", "|---" * (len(COSTS) + 2) + "|"]
    results = {}
    for vname, t in trades.items():
        results[vname] = {cn: (equity_for(t, cv, all_days), metrics(equity_for(t, cv, all_days), t, cv))
                          for cn, cv in COSTS.items()}
        L.append(f"| {vname} | {len(t):,} | " + " | ".join(f"${results[vname][cn][1]['Final value']:,.0f}" for cn in COSTS) + " |")

    focus = "0.02% (pro futures)"
    L += ["", f"## Detail at {focus} costs", "",
          "| Variant | CAGR | Max drawdown | Sharpe | Win rate | Profit factor | Avg leverage |",
          "|---|---|---|---|---|---|---|"]
    for vname in trades:
        s = results[vname][focus][1]
        L.append(f"| {vname} | {s['CAGR']:+.1%} | {s['Max drawdown']:.1%} | {s['Sharpe']:.2f} | {s['Win rate']:.1%} | "
                 f"{s['Profit factor']:.2f} | {s['Avg leverage']:.1f}x |")

    L += ["", "## Year by year (fresh $1,000 each 1 January)", ""]
    for cn in ["0.02% (pro futures)", "0.05% (retail)"]:
        L += [f"**{cn} costs**", "", "| Variant | " + " | ".join(str(y) for y in range(2020, 2027)) + " |",
              "|---" * 8 + "|"]
        for vname, t in trades.items():
            cv = COSTS[cn]
            net = (t["lev"] * (t["gross"] - cv * t["turnover"]))
            cells = []
            for y in range(2020, 2027):
                g = net[net.index.year == y]
                cells.append(f"${CAPITAL * (1 + g).prod():,.0f}")
            L.append(f"| {vname} | " + " | ".join(cells) + " |")
        L.append("")

    full = "V3 + trend & volume filters (full pro)"
    t = trades[full]
    L += ["## Stability check for the full pro version (0.02% costs)", "",
          "| Period | Trades | Win rate | Profit factor | Annual return |", "|---|---|---|---|---|"]
    for label, sl in [("2020-2023", slice("2020", "2023")), ("2024-Oct 2026", slice("2024", "2026"))]:
        sub = t.loc[sl]
        net = sub["lev"] * (sub["gross"] - COSTS[focus] * sub["turnover"])
        yrs = len(pd.date_range(sub.index[0], sub.index[-1])) / 365.25
        wins, losses = net[net > 0].sum(), -net[net < 0].sum()
        L.append(f"| {label} | {len(sub)} | {(net > 0).mean():.1%} | {wins / losses:.2f} | {(1 + net).prod() ** (1 / yrs) - 1:+.1%} |")
    L += ["", "![Pro ORB](pro_orb.png)", ""]
    (OUT / "PRO_ORB.md").write_text("\n".join(L))
    plot(results)
    print("\n".join(L))


def plot(results):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(14, 5.5), sharey=True)
    for a, cn in zip(ax, ["0.02% (pro futures)", "0.05% (retail)"]):
        for vname, by_cost in results.items():
            eq = by_cost[cn][0]
            a.plot(eq.index, eq, label=vname, linewidth=1.5 if vname.startswith("V3") else 1.1)
        a.axhline(CAPITAL, color="grey", linestyle=":", linewidth=1)
        a.set_yscale("log")
        a.set_title(f"Costs {cn}")
        a.grid(alpha=0.3, which="both")
    ax[0].set_ylabel(r"Account value (USD, log scale, start \$1,000)")
    ax[0].legend(fontsize=8, loc="upper left")
    fig.suptitle("Pro-style opening-range breakout on BTC, 2020-2026")
    fig.tight_layout()
    fig.savefig(OUT / "pro_orb.png", dpi=115)


if __name__ == "__main__":
    main()
