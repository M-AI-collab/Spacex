# AI Trend + Risk Parity Trading Bot

A monthly-rebalancing, multi-asset ETF bot built on the most *replicable* ideas from the
research in [`../legendary-trader-strategies-report.md`](../legendary-trader-strategies-report.md):

| Component | Inspired by | What it does |
|---|---|---|
| **Trend following** | Paul Tudor Jones's 200-day rule, Turtle traders, managed futures (AQR's 110-year study) | Holds an ETF only when it beats T-bills over 1, 3, 6 and 12 months. Position scaled by how many horizons agree. |
| **Risk parity** | Ray Dalio's All Weather | Inverse-volatility weighting across stocks, bonds, gold, commodities, REITs. Portfolio targets 10% annual volatility. |
| **AI layer** | Jim Simons-style quant (heavily simplified) | Gradient-boosted classifier predicts whether each ETF beats T-bills over the next month. Re-trained from scratch at every rebalance using **only past data** (walk-forward). Blended 50/50 with the trend score. |
| **Risk rules** | All of the above | No leverage, max 25% per ETF, idle cash in T-bills (BIL), next-day execution, 10 bps cost per trade side. |

Universe: SPY, QQQ, IWM, EFA, EEM, TLT, IEF, GLD, DBC, VNQ (+ BIL as cash).

All parameters were fixed **before** running the 2020-2026 test and were not tuned on it.

## Results (2 Jan 2020 to 30 Oct 2026, $1,000 start)

Full tables: [`results/RESULTS.md`](results/RESULTS.md) · Chart: [`results/equity_curve.png`](results/equity_curve.png)

| Strategy | Final value | CAGR | Volatility | Sharpe | Max drawdown |
|---|---|---|---|---|---|
| **AI Trend + Risk Parity bot** | **$1,410** | **+5.2%** | 10.4% | 0.28 | -19.7% |
| Trend + Risk Parity (no AI) | $1,602 | +7.1% | 10.1% | 0.47 | -16.4% |
| Static Risk Parity | $1,479 | +5.9% | 10.3% | 0.35 | -20.9% |
| 60/40 SPY/AGG | $1,823 | +9.2% | 12.5% | 0.55 | -21.5% |
| S&P 500 buy & hold | $2,554 | +14.7% | 20.0% | 0.65 | -33.7% |

## Honest findings

1. **The AI layer made things worse.** Out of sample its predictions had an AUC of 0.43,
   worse than a coin flip (0.50), and it cut returns by ~2% a year versus the plain trend
   version. The model learned pre-2020 patterns (e.g., bonds rally when stocks fall) that broke in
   2022, when stocks and bonds crashed together. This is a common real-world result: simple ML on
   public price data rarely has an edge.
2. **Nothing beat simply holding the S&P 500 in 2020-2026**, even on a risk-adjusted basis. This
   was an unusually strong, US-tech-led bull market. Diversified, volatility-targeted strategies
   are designed to give up upside in exchange for smaller crashes.
3. **Where trend + risk parity earns its keep is crashes.** In a separate check (trend version, no
   AI, July 2007 to 2019), it returned 6.0% a year with a Sharpe of 0.66 and a -16.9% max
   drawdown, and was roughly flat in 2008, while the S&P 500 returned 8.7% a year with a Sharpe of
   0.49, fell 36.8% in 2008 and suffered a -55.2% max drawdown.
4. **Recommendation:** if you run anything, run the **no-AI trend + risk parity version**, or simply
   hold a low-cost index fund / 60/40 core. Treat the AI layer as an experiment, not an edge.

## Limitations

- One market regime (2020-2026); ~6.8 years is short for judging a strategy.
- ETF universe chosen with general knowledge of what exists today (mild selection bias).
- Yahoo Finance adjusted prices; costs modelled at 10 bps per side, no taxes.
- Past performance does not guarantee future results. Educational project, not financial advice.

## Usage

```bash
pip install -r requirements.txt
python run_backtest.py            # uses cached data in data/prices.csv
python run_backtest.py --refresh  # re-download latest prices
```

Outputs go to `results/`: `RESULTS.md`, `equity_curve.png`, `metrics.csv`, `yearly_returns.csv`,
`equity_curves.csv`, and `ai_bot_monthly_weights.csv` (the bot's target allocation at each month end;
the last row is the current signal). The bot does not place orders; connecting a broker API would be a
separate step and should start on a paper-trading account.

## Files

- `config.py`: universe and all parameters
- `data.py`: price download and cache
- `signals.py`: trend score, ML features, walk-forward model
- `backtest.py`: position sizing, daily simulation, metrics
- `run_backtest.py`: runs everything and writes the reports
