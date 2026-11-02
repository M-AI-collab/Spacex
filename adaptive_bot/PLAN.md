# Plan: Can an AI trading bot turn $1,000 into $30,000 in one year?

## 1. The maths of the goal

| Item | Value |
|---|---|
| Target | $1,000 to $30,000 in 12 months = **30x, +2,900%** |
| Required monthly compounding | **+32.7% every month**, with no losing months to spare |
| Best audited/reconstructed track records (from our research report) | Medallion ~39%/yr net, Buffett 19.9%/yr, Druckenmiller/Soros ~30%/yr |
| Gap | The goal is **~75x the best fund's annual return** |

No unlevered strategy in our earlier research or backtests comes close (best: BTC buy & hold +41.6%/yr
in 2020-2026, with a -77% crash along the way). A 30x year therefore requires **all three** of:

1. **A very volatile market** (crypto, where 3-10x moves happen in bull years).
2. **Leverage** (2-5x+ effective exposure).
3. **A strong trending year** to ride (e.g., 2020-21). In sideways or bear years it is not reachable.

The cost: with leverage, a single sharp move against the position can liquidate the account. The
backtest must therefore measure **probability of success vs probability of ruin**, not just the best case.

## 2. Strategy design: Adaptive Regime Bot

Market: BTC, ETH, SOL, BNB perpetual futures (24/7, deep liquidity, long and short).
Data: Binance 4-hour bars, 2019-2026, plus real historical funding rates.

### Layer 1: Regime detection (per asset, every 4 hours)
| Regime | Rule (only past data) |
|---|---|
| **Bull trend** | Majority of 7/30/90-day momentum positive AND price above 50-day EMA |
| **Bear trend** | Majority of 7/30/90-day momentum negative AND price below 50-day EMA |
| **Range / chop** | Anything else |
| **Volatility state** | Realised 30-day volatility, used to size positions (high vol = smaller size) |

### Layer 2: Three specialist strategies
| Strategy | Active in | Logic |
|---|---|---|
| **Trend** | Bull / Bear | Long in bull regime, short in bear regime |
| **Breakout** (Donchian) | Any | Long on 20-day high, short on 20-day low, exit on 10-day opposite extreme |
| **Mean reversion** | Range only | Fade 2-sigma stretches from the 5-day mean, exit near the mean |

### Layer 3: AI allocator (online learning)
Every day the bot re-weights the three specialists using the **Hedge / multiplicative-weights**
online-learning algorithm: weights proportional to exp(1 x trailing 60-day Sharpe ratio), with a
10% floor each. Strategies that work in the current market get more capital automatically;
strategies that stop working fade out. This is the "adaptive" part: no human re-tuning.

### Layer 4: Risk engine
| Rule | Setting |
|---|---|
| Volatility targeting | Position size = target volatility / asset volatility, split across assets |
| Risk level (tested) | Risk budgets of 30%, 60%, 100%, 200%, 300%, 500% target volatility for a full-conviction portfolio (realised volatility is reported, as it ends up much lower) |
| Leverage caps | Max 5x per asset, max 10x total |
| Drawdown circuit breaker | Drawdown > 25% from peak: risk halved. Drawdown > 40%: risk quartered |
| Trade filter | Only rebalance when the position changes by > 10% of target (saves fees) |
| Liquidation model | If worst-case intrabar equity falls below maintenance margin (0.5% of notional), the account is liquidated (equity = $0) |
| Costs | 0.05% per side (taker fee + slippage) + **actual Binance funding rates** |

All parameters are set **before** testing and are not tuned on the results.

## 3. Backtest design
1. **Full period**: 1 Jan 2020 to 31 Oct 2026, $1,000 start, each risk level.
2. **Every calendar year**, fresh $1,000 each year: did it reach $30k?
3. **Every rolling 12-month window** (a new one starting each month, 70 windows): the share that
   reached $30k, the share that lost > 90%, and the median outcome. This is the honest
   "probability" answer.

## 4. Realistic alternative path to $30k (no backtest needed)
Trading returns on $1,000 are tiny in dollar terms, even when excellent. A strong 20% year = $200.
The reliable route to $30k in a year is **income**: a skill that pays (coding, AI automation
services for local businesses, freelancing) saving ~$2,500/month, invested sensibly. The trading
bot is best treated as a learning project with money you can afford to lose.
