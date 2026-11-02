"""Price data: download adjusted closes from Yahoo Finance and cache them locally."""

from pathlib import Path

import pandas as pd

from config import ALL_TICKERS, DATA_START

CACHE = Path(__file__).parent / "data" / "prices.csv"


def load_prices(refresh: bool = False) -> pd.DataFrame:
    """Return a DataFrame of dividend-adjusted daily closes (rows = dates, cols = tickers)."""
    if CACHE.exists() and not refresh:
        return pd.read_csv(CACHE, index_col=0, parse_dates=True)

    import yfinance as yf

    raw = yf.download(ALL_TICKERS, start=DATA_START, auto_adjust=True, progress=False)
    prices = raw["Close"][ALL_TICKERS].dropna(how="all").ffill()
    missing = [t for t in ALL_TICKERS if prices[t].isna().all()]
    if missing:
        raise RuntimeError(f"No data downloaded for: {missing}")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    prices.round(4).to_csv(CACHE)
    return prices
