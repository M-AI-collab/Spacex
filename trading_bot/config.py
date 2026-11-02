"""Strategy configuration.

Every parameter here was set from published research / standard practice
BEFORE running the 2020-2026 backtest. They are deliberately not tuned on the
test period, to avoid curve-fitting.
"""

# Diversified, liquid, retail-accessible ETFs (stocks, bonds, gold, commodities, REITs).
RISKY_ASSETS = [
    "SPY",  # US large caps
    "QQQ",  # US tech / Nasdaq-100
    "IWM",  # US small caps
    "EFA",  # Developed ex-US equities
    "EEM",  # Emerging-market equities
    "TLT",  # Long-term US Treasuries
    "IEF",  # 7-10y US Treasuries
    "GLD",  # Gold
    "DBC",  # Broad commodities
    "VNQ",  # US REITs
]
CASH_ASSET = "BIL"          # 1-3 month T-bills: where unallocated capital sits
BENCHMARK_BOND = "AGG"      # used only for the 60/40 benchmark
ALL_TICKERS = RISKY_ASSETS + [CASH_ASSET, BENCHMARK_BOND]

DATA_START = "2005-01-01"   # history for indicators and ML training (pre-2020 only for first model)
BACKTEST_START = "2020-01-01"
BACKTEST_END = None         # None = latest available data

# Trend signal: multi-horizon time-series momentum (AQR "Century of Evidence" style).
MOMENTUM_LOOKBACKS = [21, 63, 126, 252]   # ~1, 3, 6, 12 months of trading days

# Machine-learning layer.
ML_HORIZON = 21              # predict the next ~1 month return vs T-bills
ML_TRAIN_START = "2007-06-01"
ML_BLEND = 0.5               # final score = 50% trend + 50% ML
ML_PROB_FLOOR = 0.50         # probability <= 50% -> no ML conviction
ML_PROB_FULL = 0.60          # probability >= 60% -> full ML conviction

# Risk management.
VOL_LOOKBACK = 63            # ~3 months for volatility / covariance estimates
TARGET_VOL = 0.10            # 10% annualised portfolio volatility target
MAX_GROSS_EXPOSURE = 1.0     # no leverage (retail-friendly)
MAX_ASSET_WEIGHT = 0.25      # no single ETF above 25%
EXECUTION_LAG_DAYS = 1       # signal at close, trade at next close (no look-ahead)
COST_PER_TURNOVER = 0.0010   # 10 bps per unit traded (commission + spread + slippage)

TRADING_DAYS = 252
