# Adaptive Regime Bot: the $1,000 to $30,000 in one year test

Goal: turn **$1,000 into $30,000 in 12 months** (30x) with an adaptive AI trading bot.
Plan and maths: [`PLAN.md`](PLAN.md) · Full tables: [`results/RESULTS.md`](results/RESULTS.md) · Chart: [`results/results.png`](results/results.png)

## How the bot works

```
4h price data (BTC, ETH, SOL, BNB perps)
        │
        ▼
Regime detector (per asset) ──► Bull trend / Bear trend / Range + volatility state
        │
        ▼
3 specialists:  Trend (long bull / short bear) · Breakout (Donchian 20/10) · Mean reversion (range only)
        │
        ▼
AI allocator (online learning, Hedge algorithm): re-weights specialists daily by trailing 60-day Sharpe
        │
        ▼
Risk engine: volatility targeting · 5x/asset & 10x total leverage caps · drawdown circuit breaker
             · rebalance band · fees 0.05%/side · real Binance funding · liquidation model
```

The bot adapts on its own. Each asset is classified bull, bear or range every 4 hours. Shorts are
taken in bear markets, mean reversion runs only in ranges, and the allocator moves capital toward
whichever specialist is currently working. In 2021 it put 45% on trend; in 2025, 52% on mean reversion.

## Results (1 Jan 2020 to 31 Oct 2026, real Binance data)

### Did any 12-month period reach $30k? (71 rolling windows, fresh $1,000 each)

| Risk level | Realised vol | Reached $30k | Ended in profit | Liquidated or lost >90% | Median result | Best 12 months |
|---|---|---|---|---|---|---|
| L1 Conservative | 15% | **0 / 71** | 75% | 0% | $1,095 | $1,540 |
| L2 Moderate | 26% | **0 / 71** | 70% | 0% | $1,132 | $2,314 |
| L3 Aggressive | 37% | **0 / 71** | 63% | 0% | $1,078 | $3,792 |
| L4 Very aggressive | 55% | **0 / 71** | 51% | 0% | $1,011 | $5,111 |
| L5 Extreme | 68% | **0 / 71** | 51% | 0% | $1,000 | $6,826 |
| L6 Maximum | 193% | **0 / 71** | 21% | **21%** | $553 | $9,570 |
| BTC buy & hold | ~60% | **0 / 71** | 61% | 0% | $1,545 | $9,223 |

### Calendar years ($1,000 every 1 January)

| Year | L1 | L2 | L3 | L4 | L5 | L6 | BTC hold |
|---|---|---|---|---|---|---|---|
| 2020 | $1,221 | $1,457 | $1,533 | $1,555 | $1,847 | $0 (liquidated) | $4,003 |
| 2021 | $1,390 | $1,890 | $2,660 | $3,087 | $3,763 | $5,613 | $1,579 |
| 2022 | $1,040 | $1,001 | $1,043 | $1,011 | $702 | $553 | $353 |
| 2023 | $1,267 | $1,561 | $1,615 | $2,075 | $1,767 | $1,284 | $2,558 |
| 2024 | $844 | $770 | $719 | $575 | $366 | $288 | $2,211 |
| 2025 | $1,025 | $1,031 | $1,026 | $666 | $561 | $504 | $934 |
| 2026 (Jan-Oct) | $1,044 | $1,073 | $940 | $974 | $922 | $1,130 | $883 |

### One account over the whole period (never topped up)

| Risk level | Final value | CAGR | Max drawdown | Sharpe |
|---|---|---|---|---|
| L1 Conservative | $1,774 | +8.8% | -29.1% | 0.64 |
| L2 Moderate | $2,799 | +16.3% | -36.7% | 0.71 |
| **L3 Aggressive** | **$4,131** | **+23.1%** | -45.8% | **0.74** |
| L4 Very aggressive | $3,735 | +21.3% | -58.8% | 0.63 |
| L5 Extreme | $3,472 | +20.0% | -75.2% | 0.63 |
| L6 Maximum | $0 | liquidated Aug 2020 | -100% | - |
| BTC buy & hold | $10,738 | +41.6% | -77.0% | - |

### Hindsight upper bound ([`hindsight.py`](hindsight.py))

Even with **perfect knowledge of the future** (best start month and best constant leverage on BTC),
only **1 of 71** start months could reach $30k: buying BTC at ~4x leverage on 1 April 2020, right
after the COVID crash (to ~$106k). Without hindsight, fixed 5x leverage on BTC was liquidated in
21% of windows, with a median result of $33.

## Honest conclusion

1. **$30k in one year from $1,000 did not happen in any of 71 real 12-month periods**, at any risk level.
   The best the bot ever did was $9,570, and that setting (L6) also got liquidated in 21% of windows.
2. **More leverage stopped helping beyond L3.** Returns peaked at the "Aggressive" level
   (+23.1%/yr, Sharpe 0.74). Above that, fees, funding (up to 30%+/yr for longs in 2021) and deeper
   drawdowns ate the gains, and L6 was wiped out.
3. **The adaptive design does protect capital.** In 2022 (BTC -65%), L1-L4 finished flat to slightly
   positive by going short and cutting risk. 2024 was its worst year: choppy reversals whipsawed the
   trend and breakout specialists.
4. **Recommendation:** the realistic version is L2-L3: roughly +15-25% a year with 35-45% drawdowns.
   On $1,000 that is $150-250 a year. The fastest path to $30k is income and savings, not leverage
   (see `PLAN.md`, section 4).

## Limitations

- Spot prices used as a proxy for perpetual futures prices; actual funding rates are applied.
- 4-hour bars: liquidation is checked on 4h highs/lows (conservative), and execution is assumed at bar close plus 0.05%.
- One test period (2020-2026). Parameters were fixed up front and not optimised.
- Past performance does not guarantee future results. Educational project, not financial advice.

## Usage

```bash
pip install pandas numpy matplotlib
python run_backtest.py   # first run downloads ~25 MB of Binance archives into data/ (gitignored)
python hindsight.py      # hindsight upper bound
```

Files: `data.py` (download), `strategy.py` (regimes, specialists, AI allocator), `simulator.py`
(leveraged account with funding, fees, liquidation), `run_backtest.py` (all tests and reports).
