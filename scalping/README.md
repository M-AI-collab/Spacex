# BTC Scalping Strategy Backtests (2020-2026)

Four classic scalping strategies tested on **3.59 million 1-minute BTC/USDT bars** from Binance's
public archive, 1 Jan 2020 to 31 Oct 2026, starting with **$1,000**.

Full tables: [`results/RESULTS.md`](results/RESULTS.md) · Chart: [`results/equity_curves.png`](results/equity_curves.png)

## Strategies (textbook parameters, fixed before testing)

| # | Strategy | Timeframe | Entry | Exit |
|---|---|---|---|---|
| 1 | VWAP mean reversion | 1m | Price stretches 2.5 std devs from the daily VWAP | Back at VWAP · stop 4 std devs · 60-min time stop |
| 2 | Bollinger + RSI(2) reversion | 5m | Close outside Bollinger Band (20, 2) with RSI(2) < 10 / > 90 | Back at 20-bar mean · stop 1.5x ATR · 2h time stop |
| 3 | EMA 9/21 crossover + 1h trend | 5m | EMA 9/21 cross in the direction of the 1-hour EMA-50 trend | Stop 1x ATR · target 2x ATR · opposite cross · 4h time stop |
| 4 | US opening-range breakout | 1m | First break of the 09:30-10:00 ET range, 10:00-12:00 ET, one trade per day | Stop at opposite side of range · exit 16:00 ET |

Common rules: signal on bar close, entry at next bar's open, 100% of equity per trade, no leverage,
long and short, stop assumed to hit first if stop and target are touched in the same bar.

## Results: final value of $1,000

| Strategy | No costs | 0.02%/side | **0.05%/side (typical retail)** | 0.10%/side | Break-even cost |
|---|---|---|---|---|---|
| VWAP mean reversion | $451 | < $0.01 | **< $0.01** | < $0.01 | none, loses even with zero costs |
| Bollinger + RSI(2) | $152,049 | $0.01 | **< $0.01** | < $0.01 | 0.006% per side |
| EMA 9/21 crossover | $992 | $1.97 | **< $0.01** | < $0.01 | none, no edge |
| Opening-range breakout | $7,588 | $3,865 | **$1,405** | $260 | 0.060% per side |
| *BTC buy & hold* | | | **$10,782** | | |

## Honest findings

1. **Three of four strategies wiped out the account at realistic costs.** At 0.05% per side,
   VWAP reversion was below $100 by May 2020 and below $10 by September 2020. Bollinger/RSI(2) went
   under $10 by November 2020. The EMA crossover went under $10 by January 2022.
2. **Costs, not the signals, decide everything.** The average scalp moves only about 0.001-0.014%
   before costs, while a round trip costs 0.04-0.20%. Bollinger/RSI(2) shows a genuine tiny edge
   ($1,000 to $152,049 with zero costs, from 40,000+ trades), but it needs costs under 0.006% per side,
   which only market makers with exchange rebates and fast infrastructure get.
3. **Only the opening-range breakout survived, and only barely.** At 0.05% per side it turned
   $1,000 into $1,405 (+5.1% a year) with a -42.8% max drawdown and a Sharpe of 0.33. It lost money
   in 4 of 7 years (2020, 2021, 2025, 2026), its break-even cost is 0.060% per side (almost exactly
   what retail traders pay), and it fails at spot fees (0.10%: $260). Picking the best of four tested
   strategies also flatters it. This is not a reliable edge.
4. **BTC buy & hold beat everything:** $10,782 (+41.6% a year), but with a -76.6% max drawdown.
5. This matches the academic evidence in the earlier report: high-frequency retail trading loses
   mainly through costs.

## Limitations

- Spot prices used as a proxy for perpetual futures. Funding payments are ignored (small for trades
  lasting minutes to hours).
- Costs are modelled as a flat % per side; real slippage on stops in fast markets is often worse.
- 1-minute bars cannot show the order of moves inside a minute; the stop-first rule is conservative.
- No parameter optimisation was done. Tuning would improve past results but would also overfit.
- Past performance does not guarantee future results. Educational project, not financial advice.

## Usage

```bash
pip install pandas numpy matplotlib
python run_scalping.py   # downloads ~170 MB of Binance archives to data/ on first run (gitignored)
```

Files: `data.py` (download and parsing), `strategies.py` (the four strategies), `engine.py`
(trade simulator and metrics), `run_scalping.py` (runs everything and writes `results/`).
