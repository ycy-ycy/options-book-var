import math
import numpy as np
import pandas as pd
from datetime import date
from positions import Position, Option
from hs_data import load_closes, build_moves
import matplotlib.pyplot as plt

def per_position_daily_return(book: list[Position], today: date, rate: float, window: int=500, filtered: bool=True) -> np.ndarray:
    # Yahoo's range ends today (not at `today`) and a year has ~251 trading days: one spare year
    closes = load_closes(book, today, f"{math.ceil(window / 252) + 1}y")
    moves = build_moves(closes, window, filtered)
    historical_returns = {c: moves[c].to_numpy() for c in moves.columns}

    _per_position_daily_return = []

    for position in book:
        ticker = position.ticker
        r = historical_returns.get(ticker, None)
        assert r is not None, f"no price moves for {position.ticker}"
        if isinstance(position, Option):
            v = historical_returns.get(position.proxy.value, None)
            assert v is not None, f"no vol moves for {position.proxy.value} ({position})"
        else:   # stocks carry no vol exposure
            v = np.zeros_like(r)
        
        spot = closes[ticker].iloc[-1]
        position_daily_return = position.dollar_pnl(spot, r, today, rate, v)
        _per_position_daily_return.append(position_daily_return[:, np.newaxis])

    return np.concat(_per_position_daily_return, axis=1)

def per_ticker_daily_return(book: list[Position], per_position: np.ndarray) -> dict[str, np.ndarray]:
    tickers = np.array([p.ticker for p in book])
    return {t: per_position[:, tickers == t].sum(axis=1) for t in dict.fromkeys(p.ticker for p in book)}

def total_daily_return(per_position: np.ndarray) -> np.ndarray:
    return per_position.sum(axis=1)

def HS(book: list[Position], today: date, rate: float=0, window: int=500, filtered: bool=True, plot: bool=True, bins: int=40) -> np.ndarray:
    _per_position_daily_return = per_position_daily_return(book, today, rate, window, filtered)

    # portfolio HS
    print("Portfolio Simulation Results")
    r = total_daily_return(_per_position_daily_return)
    if plot:
        plt.hist(r, bins=bins)
        plt.show()
    print(f"Avg Return = {np.average(r): .2f}")
    indexed_sorted_r = sorted(enumerate(r), key=lambda x: x[1])
    sorted_r = [r for idx, r in indexed_sorted_r]
    p99 = 0.01 * window
    p97_5 = 0.025 * window
    portfolio_var99 = -sorted_r[math.floor(p99)]
    portfolio_es97_5 = -(sum(sorted_r[:math.floor(p97_5)]) + (p97_5 - math.floor(p97_5)) * sorted_r[math.floor(p97_5)]) / p97_5
    print(f"VaR99 = {portfolio_var99: .2f}")
    print(f"ES97.5 = {portfolio_es97_5: .2f}")

    # component
    print("\nComponent Contribution")
    ticker_r = per_ticker_daily_return(book, _per_position_daily_return)
    idx_99 = indexed_sorted_r[math.floor(p99)][0]
    idx_97_5 = [idx for idx, r in indexed_sorted_r[:math.floor(p97_5)]]
    idx_97_5_boundary = indexed_sorted_r[math.floor(p97_5)][0]
    for ticker, ticker_ret in ticker_r.items():
        es97_5 = -(sum([ticker_ret[i] for i in idx_97_5]) + (p97_5 - math.floor(p97_5)) * ticker_ret[idx_97_5_boundary]) / p97_5
        print(f"{ticker}: ES97.5: {es97_5: .2f} ({es97_5 / portfolio_es97_5 * 100: .2f}%)")

    # per-ticker standalone
    print("\nStandalone Simulation")
    for ticker, ticker_ret in ticker_r.items():
        avg = np.average(ticker_ret)
        sorted_ticker_ret = sorted(ticker_ret)
        var99 = -sorted_ticker_ret[math.floor(p99)]
        es97_5 = -(sum(sorted_ticker_ret[:math.floor(p97_5)]) + (p97_5 - math.floor(p97_5)) * sorted_ticker_ret[math.floor(p97_5)]) / p97_5
        print(f"{ticker}: Avg Return: {avg: .2f}; VaR99: {var99: .2f}; ES97.5: {es97_5: .2f}")

    return _per_position_daily_return


if __name__ == "__main__":
    from positions_loader import load_positions

    HS(*load_positions("./positions.example.json"))