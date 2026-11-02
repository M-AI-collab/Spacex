"""Binance public-archive data: 4-hour spot bars (price proxy for perps) and perpetual funding rates.

Raw zips are cached in data/raw/ (gitignored).
"""

import io
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ASSETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
FIRST = (2019, 1)
LAST = (2026, 10)
RAW = Path(__file__).parent / "data" / "raw"
BASE = "https://data.binance.vision/data"


def _months(first=FIRST, last=LAST):
    y, m = first
    while (y, m) <= last:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def _fetch(url: str, path: Path) -> bool:
    if path.exists():
        return path.stat().st_size > 0
    try:
        urllib.request.urlretrieve(url, path)
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:          # asset not listed yet that month
            path.write_bytes(b"")
            return False
        raise


def _read_zip(path: Path, **kw) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        return pd.read_csv(io.BytesIO(z.read(z.namelist()[0])), **kw)


def _to_utc(ts: pd.Series) -> pd.DatetimeIndex:
    ts = ts.astype("int64")
    ts = ts.where(ts < 10**14, ts // 1000)  # microseconds from 2025 onward
    return pd.to_datetime(ts, unit="ms", utc=True)


def load_klines(symbol: str) -> pd.DataFrame:
    RAW.mkdir(parents=True, exist_ok=True)
    parts = []
    for y, m in _months():
        f = RAW / f"{symbol}-4h-{y}-{m:02d}.zip"
        if _fetch(f"{BASE}/spot/monthly/klines/{symbol}/4h/{symbol}-4h-{y}-{m:02d}.zip", f):
            df = _read_zip(f, header=None, usecols=[0, 1, 2, 3, 4])
            if not str(df.iloc[0, 0]).isdigit():   # some files have a header row
                df = df.iloc[1:]
            parts.append(df.astype(float))
    df = pd.concat(parts)
    df.index = _to_utc(df[0])
    df = df.drop(columns=0)
    df.columns = ["open", "high", "low", "close"]
    return df[~df.index.duplicated()].sort_index()


def load_funding(symbol: str) -> pd.Series:
    parts = []
    for y, m in _months((2020, 1)):
        f = RAW / f"{symbol}-funding-{y}-{m:02d}.zip"
        url = f"{BASE}/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{y}-{m:02d}.zip"
        if _fetch(url, f):
            df = _read_zip(f)
            parts.append(pd.Series(df["last_funding_rate"].to_numpy(), index=_to_utc(df["calc_time"])))
    s = pd.concat(parts).sort_index()
    return s[~s.index.duplicated()]


def load_all():
    """Return dict of OHLC frames on a common 4h grid, and funding cost per 4h bar per asset."""
    bars = {s: load_klines(s) for s in ASSETS}
    grid = pd.date_range(min(b.index[0] for b in bars.values()),
                         max(b.index[-1] for b in bars.values()), freq="4h", tz="UTC")
    bars = {s: b.reindex(grid) for s, b in bars.items()}
    funding = pd.DataFrame(index=grid)
    for s in ASSETS:
        f = load_funding(s)
        # funding settles at 00/08/16 UTC; floor to the 4h bar that is open just before settlement
        f.index = (f.index - pd.Timedelta(minutes=1)).floor("4h")
        funding[s] = f.groupby(level=0).sum().reindex(grid).fillna(0.0)
    return bars, funding
