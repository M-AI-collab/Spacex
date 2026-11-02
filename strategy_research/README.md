# Strategy Research: best honest bot, overfitting demo, and a real plan to $30k/year

Three parts, all on real Binance data (BTC, ETH, SOL, BNB perpetuals, daily bars, Jan 2020 to Oct 2026),
with 0.05%/side costs, actual funding rates, leverage caps and liquidation modelled.

| Part | Question | File | Results |
|---|---|---|---|
| 1 | What is the best strategy that holds up on **unseen** data? | `search.py`, `robustness.py` | [`results/RESULTS.md`](results/RESULTS.md), [`results/ROBUSTNESS.md`](results/ROBUSTNESS.md) |
| 2 | How do "$30k a year" bots get made, and why do they fail? | `overfit_demo.py` | [`results/OVERFIT_DEMO.md`](results/OVERFIT_DEMO.md) |
| 3 | What does it actually take to make $30k a year from trading? | `wealth_plan.py` | [`results/WEALTH_PLAN.md`](results/WEALTH_PLAN.md) |

## Part 1: honest strategy search

**Method.** 180 configurations: 6 strategy families (time-series momentum, moving-average crossover,
Donchian breakout, RSI reversion, Bollinger reversion, cross-sectional momentum) x parameters x
long-only/long-short x 3 risk levels. Two out-of-sample tests:

- **Fixed split:** choose on 2020-2023, judge on Jan 2024-Oct 2026.
- **Walk-forward:** each year from 2022, the bot picks the strategy with the best Sharpe *using only earlier
  years*, trades it for the year, then repeats.

Plus a **pre-registered baseline** (TSMOM 20/60/120-day, long-only, set from the literature before running anything),
the **Deflated Sharpe Ratio** to correct for the number of strategies tried, and a **survivorship check**.

**Winner: cross-sectional momentum.** Every 24 hours, hold the 2 coins with the strongest 30-day return
(only if that return is positive), each sized by its volatility. The walk-forward chose it every year.

| Walk-forward, Jan 2022 to Oct 2026 | 2022 | 2023 | 2024 | 2025 | 2026* | CAGR | Sharpe | Max DD |
|---|---|---|---|---|---|---|---|---|
| Winner @ 30% vol | $889 | $1,739 | $1,270 | $1,274 | $1,118 | +23.7% | 1.03 | -23.2% |
| Winner @ 60% vol | $753 | $2,857 | $1,527 | $1,549 | $1,185 | +45.0% | 1.03 | -41.9% |
| Winner @ 100% vol | $558 | $5,085 | $1,795 | $1,868 | $1,180 | +65.0% | 1.03 | -61.3% |
| Pre-registered TSMOM baseline | $717 | $2,015 | $1,782 | $1,117 | $995 | +24.3% | 0.80 | -35.6% |
| BTC buy & hold | $358 | $2,556 | $2,213 | $937 | $885 | +11.3% | 0.46 | -66.9% |

*Value of a fresh $1,000 each year; 2026 is Jan-Oct.*

**But apply these haircuts before believing it:**

| Check | Result |
|---|---|
| Survivorship: same strategy without SOL | +32.5%/yr, Sharpe 0.84 |
| Survivorship: wider 10-coin universe incl. FTT (collapsed 2022) | **+14.3%/yr, Sharpe 0.52, max DD -61%** |
| Deflated Sharpe Ratio (60 strategies tried) | 50%: not statistically proven |
| Strategies whose Sharpe fell on unseen data | 83%; median Sharpe 1.13 to 0.40 |
| Calendar years where any of the 180 configs turned $1,000 into $30,000 | **0 of 1,260** (best: $21,093, found only in hindsight) |

**Realistic expectation:** roughly **15-30% a year** with 25-45% drawdowns at moderate risk. That's good
(better than BTC buy & hold over 2022-2026 on a risk-adjusted basis), but it is nowhere near 30x.

## Part 2: the fake "$30k a year" AI bot

A deep ExtraTrees model trained on 2020-2023 to predict each coin's next-day direction:

| | Direction accuracy | Value of $1,000 |
|---|---|---|
| **Backtested on the data it learned from** (2020-23) | 100% | Up to **$8.3 billion in one year** (2021); $30k+ in 3 of 4 years |
| **On new data** (2024-26) | 48.9% | $878 · $1,589 · $479 (-13%/yr) |

The model memorised the past. Any bot advertised with near-perfect backtests or "30x a year" is very
likely this, or a scam. Ask for **live, audited, multi-year** results instead.

## Part 3: the real path to $30k a year

$30k/year of profit = capital x return. At an honest 15-25%, that requires **$120k-$200k of capital**.

| Monthly savings into the bot | at 15%/yr | at 25%/yr |
|---|---|---|
| $500 (AED 1,836) | 12.3 years | 7.5 years |
| $1,000 (AED 3,672) | 8.6 years | 5.2 years |
| $2,000 (AED 7,345) | 5.6 years | 3.4 years |
| $3,000 (AED 11,018) | 4.2 years | 2.5 years |

The biggest lever is **monthly contributions**, i.e. income. Practical plan:

1. **Now (student):** paper-trade the winner (cross-sectional momentum, 30% vol, wide coin universe) for
   6-12 months. Put real money in only once live behaviour matches the backtest. Keep most savings in a
   low-cost index fund.
2. **Build income:** your coding and AI skills can pay now. Options include AI automation for small
   businesses in Dubai (chatbots, workflow automation, lead generation), freelance Python and data work,
   or trading-tool development. Aim to save $1,000-2,000 a month.
3. **Scale gradually:** add to the bot only from savings, never borrowed money. Keep leverage at 30-60%
   volatility. The 100% volatility setting had a -61% drawdown even in the best case.
4. **Milestone check:** at $1,500/month and about 20%/yr, the account can produce about $30k a year in
   roughly 5-6 years. That's a realistic plan, not a backtest fantasy.

## Sources

- Bailey, Borwein, Lopez de Prado & Zhu, ["The Probability of Backtest Overfitting"](https://papers.ssrn.com/abstract=2326253), *Journal of Computational Finance* 20(4), 2017.
- Bailey & Lopez de Prado, ["The Deflated Sharpe Ratio"](https://papers.ssrn.com/abstract=2460551), *Journal of Portfolio Management* 40(5), 2014.
- Harvey, Liu & Zhu, ["... and the Cross-Section of Expected Returns"](https://nber.org/papers/w20592), *Review of Financial Studies* 29, 2016: most published factors are likely false; require t > 3.0.
- Suhonen, Lennkh & Perez, "Quantifying Backtest Overfitting in Alternative Beta Strategies", *JPM* 2017: median Sharpe fell 73% from backtest (1.20) to live (0.31) across 215 products ([summary](https://alphaarchitect.com/looking-at-alternatives-avoid-complexity-and-magical-backtests/)).
- Moskowitz, Ooi & Pedersen, ["Time Series Momentum"](https://papers.ssrn.com/abstract=2089463), *Journal of Financial Economics* 104(2), 2012.
- Liu & Tsyvinski, ["Risks and Returns of Cryptocurrency"](https://papers.ssrn.com/abstract=3226806), *Review of Financial Studies* 34(6), 2021: strong time-series momentum in crypto.
- Data: [Binance public data archive](https://data.binance.vision) (spot klines and USD-M funding rates).

## Limitations

- Spot prices proxy perpetual futures prices; real funding rates applied.
- The coin universe is small and partly chosen with hindsight (see the survivorship check).
- Six years, mostly one crypto cycle. Past performance does not guarantee future results.
- Educational research, not financial advice.

## Usage

```bash
pip install pandas numpy scipy scikit-learn matplotlib
python search.py          # Part 1 (uses the Binance cache from ../adaptive_bot; downloads if missing)
python robustness.py      # survivorship check (downloads 6 more coins)
python overfit_demo.py    # Part 2
python wealth_plan.py     # Part 3
```
