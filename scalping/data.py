"""BTCUSDT 1-minute bars from Binance's public archive (data.binance.vision).

Monthly zips are downloaded to data/raw/ and parsed into a cached .npz file.
The data/ folder is gitignored (hundreds of MB).
"""

import io
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOL = "BTCUSDT"
START = (2020, 1)
END = (2026, 10)
DATA = Path(__file__).parent / "data"
RAW = DATA / "raw"
CACHE = DATA / f"{SYMBOL}_1m.npz"
URL = "https://data.binance.vision/data/spot/monthly/klines/{s}/1m/{s}-1m-{y}-{m:02d}.zip"


def _months():
    y, m = START
    while (y, m) <= END:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def download() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for y, m in _months():
        path = RAW / f"{SYMBOL}-1m-{y}-{m:02d}.zip"
        if not path.exists():
            urllib.request.urlretrieve(URL.format(s=SYMBOL, y=y, m=m), path)


def _parse(path: Path) -> np.ndarray:
    with zipfile.ZipFile(path) as z:
        raw = z.read(z.namelist()[0])
    arr = np.loadtxt(io.BytesIO(raw), delimiter=",", usecols=(0, 1, 2, 3, 4, 5), ndmin=2)
    ts = arr[:, 0]
    ts = np.where(ts > 1e14, ts / 1000, ts)  # Binance switched to microseconds in 2025
    arr[:, 0] = ts
    return arr


def load_bars() -> pd.DataFrame:
    """1-minute OHLCV indexed by UTC timestamp (bar open time)."""
    if not CACHE.exists():
        download()
        parts = [_parse(RAW / f"{SYMBOL}-1m-{y}-{m:02d}.zip") for y, m in _months()]
        arr = np.vstack(parts)
        np.savez_compressed(CACHE, bars=arr)
    arr = np.load(CACHE)["bars"]
    idx = pd.to_datetime(arr[:, 0].astype("int64"), unit="ms", utc=True)
    df = pd.DataFrame(arr[:, 1:], index=idx, columns=["open", "high", "low", "close", "volume"])
    df = df[~df.index.duplicated()].sort_index()
    return df


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Aggregate to a higher timeframe; bars labelled by their open time."""
    out = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return out.dropna(subset=["open"])
