"""Price history for historical simulation: one aligned close table ending at the snapshot date."""
from datetime import date

import pandas as pd
import numpy as np

from positions import Position
from price_fetcher import fetch_closes, PROXY_TICKERS, proxy_moves

import math

LAMBDA = 0.94 # RiskMetrics decay
BURN_IN = math.ceil(math.log(0.001) / math.log(LAMBDA))


def load_closes(book: list[Position], as_of: date, rng: str = "5y") -> pd.DataFrame:
    """Closes of every ticker in the book plus the vol-index proxies, one row per NYSE day, last row = as_of.

    Spot for each ticker is the last row (adjclose; equal to the raw close unless a dividend went ex after as_of).
    VXN9D / VXN3M are synthetic: build them from the returns with price_fetcher.proxy_moves.
    """
    tickers = sorted({p.ticker for p in book})
    px = fetch_closes(tickers + PROXY_TICKERS, rng).loc[: pd.Timestamp(as_of)]
    if px.empty or px.index[-1] != pd.Timestamp(as_of):
        last = px.index[-1].date() if not px.empty else None
        raise ValueError(f"no close on {as_of}; last row is {last}")
    gaps = px.iloc[-1][px.iloc[-1].isna()].index.tolist()
    if gaps:
        raise ValueError(f"missing close on {as_of} for {gaps}")
    return px

def build_moves(closes: pd.DataFrame, window: int = 500, filtered: bool=True) -> pd.DataFrame:
    R = pd.DataFrame(np.log(closes)).diff().iloc[1:]          # first row is always NaN
    V, _ = proxy_moves(R)                                     # betas fit on the full fetched history
    moves = pd.concat([R, V[["VXN9D", "VXN3M"]]], axis=1)     # joined by date, not by position

    if moves.index.has_duplicates or not moves.index.is_monotonic_increasing:
        raise ValueError("dates are not strictly increasing")
    if len(moves) < window:
        raise ValueError(f"only {len(moves)} days of moves, need {window}")

    if filtered:   # FHS: rescale stock moves to today's EWMA vol; vol-proxy moves stay raw
        stocks = [c for c in moves.columns if c not in PROXY_TICKERS + ["VXN9D", "VXN3M"]]
        burn = moves[stocks].iloc[:-window].notna().sum()     # valid days before the window, per stock
        if (burn < BURN_IN).any():
            raise ValueError(f"EWMA needs {BURN_IN} days before the window: {burn[burn < BURN_IN].to_dict()}")
        var = (moves[stocks] ** 2).ewm(alpha=1-LAMBDA, adjust=False).mean()   # sigma^2 after each day
        sigma_t = np.sqrt(var.shift(1))                       # forecast for day t, made the day before
        sigma_today = np.sqrt(var.iloc[-1])                   # forecast for tomorrow (a Series by column)
        moves[stocks] = moves[stocks] * sigma_today / sigma_t
    
    moves = moves.iloc[-window:]

    # integrity check on the scenarios used: a NaN here is a missing or misaligned date
    # (rows before the window may be NaN, e.g. a ticker that listed after the fetch start)
    gaps = moves.isna()
    if gaps.any().any():
        cols = moves.columns[gaps.any()].tolist()
        days = moves.index[gaps.any(axis=1)]
        raise ValueError(f"missing moves for {cols} on {len(days)} day(s), first {days[0].date()}")
    return moves
