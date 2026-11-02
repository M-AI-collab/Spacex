# Part 2: the overfit 'AI bot' (do not trade this)

ExtraTrees classifier, unlimited depth, 300 trees, ~57 features per coin, trained on Jan 2020 - Dec 2023 to predict next-day direction of BTC, ETH, SOL, BNB. Long/short, 1x exposure, 0.05%/side costs + funding.

| Period | Direction accuracy | Value of $1,000 per year | CAGR | Sharpe |
|---|---|---|---|---|
| **In-sample** 2020-2023 (data it memorised) | 100.0% | 2020: $6,883, 2021: $8,294,204,493, 2022: $61,239,512, 2023: $1,691,082 | +876,773% | 16.6 |
| **Out-of-sample** 2024-Oct 2026 (unseen) | 48.9% | 2024: $878, 2025: $1,589, 2026: $479 | -13.3% | -0.10 |

In-sample years at or above the $30k goal: **3 of 4**. Out-of-sample years at or above $30k: **0 of 3**.

Why: with unlimited depth the trees memorise every training day's answer, so in-sample 'predictions' are really look-ups. On new days the same model is close to a coin flip, and fees eat the rest. This is the same mechanism behind most 'verified backtest' bot adverts.
