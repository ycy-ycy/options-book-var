from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from enum import Enum

import numpy as np
from scipy.stats import norm

from constants import TRADING_DAYS, CALENDAR_DAYS, CONTRACT_MULTIPLIER, NYSE_HOLIDAYS

class OptionType(Enum):
    CALL = "call"
    PUT = "put"
    
class Direction(Enum):
    B = 1      # buy / long
    S = -1     # sell / short

class Proxy(Enum):
    # by days to expiry: <= 14 -> 9D, <= 45 -> 30D, else 3M; VXN9D / VXN3M are synthetic
    VIX9D = "^VIX9D"
    VIX = "^VIX"
    VIX3M = "^VIX3M"
    VXN9D = "VXN9D"
    VXN = "^VXN"
    VXN3M = "VXN3M"

def bs_price(S: np.ndarray|float, K: float, T: float, sig: np.ndarray|float, opt_type: OptionType, rate: float=0.):
    if T <= 0:
        if opt_type is OptionType.CALL:
            return np.maximum(S - K, 0)
        return np.maximum(K - S, 0)

    if np.any(sig <= 0):
        raise ValueError("Non-positive volatility.")

    discount = np.exp(- rate * T)
    F = S / discount
    std = np.sqrt(sig ** 2 * T)
    d1 = np.log(F/K) / std + 0.5 * std
    d2 = d1 - std

    if opt_type is OptionType.CALL:
        return S * norm.cdf(d1) - K * discount * norm.cdf(d2)
    return K * discount * norm.cdf(-d2) - S * norm.cdf(-d1)

def iv_extraction(S: float, K: float, T:float, price: float, opt_type: OptionType, rate: float=0.) -> float:
    l = 0.01
    r = 4.00
    m = 0.5 * (l + r)

    pl = bs_price(S, K, T, l, opt_type, rate) - price
    pr = bs_price(S, K, T, r, opt_type, rate) - price
    if pl * pr > 0:
        raise ValueError("Invalid data.")

    for _ in range(100):
        pm = bs_price(S, K, T, m, opt_type, rate) - price
        pr = bs_price(S, K, T, r, opt_type, rate) - price

        if pr * pm >= 0:
            r = m
        else:
            l = m
        
        m = 0.5 * (l + r)

    return m

def iv_multiplier(n_td: int, n_cal: int) -> float:
    if n_td <= 0:
        return 0.0
    return np.sqrt((n_cal / CALENDAR_DAYS) / (n_td / TRADING_DAYS))

@dataclass
class Position(ABC):
    ticker: str
    direction: Direction
    qty: float

    @abstractmethod
    def dollar_pnl(self, spot: float, ret: np.ndarray, today: date, rate: float, v: np.ndarray) -> np.ndarray:
        ...


@dataclass
class Stock(Position):
    def __str__(self) -> str:
        sign = "+" if self.direction is Direction.B else "-"
        return f"{sign}{self.qty:g} {self.ticker} stock"

    def dollar_pnl(self, spot: float, ret: np.ndarray, today: date, rate: float, v: np.ndarray) -> np.ndarray:
        return spot * np.expm1(ret) * self.qty * self.direction.value


@dataclass
class Option(Position):
    proxy: Proxy
    opt_type: OptionType
    strike: float
    expiry: date
    iv_quote: float

    def __str__(self) -> str:
        sign = "+" if self.direction is Direction.B else "-"
        cp = "C" if self.opt_type is OptionType.CALL else "P"
        return f"{sign}{self.qty:g} {self.ticker} {self.strike:g}{cp} {self.expiry.isoformat()} (iv {self.iv_quote * 100:.1f}%)"

    def dollar_pnl(self, spot: float, ret: np.ndarray, today: date, rate: float, v: np.ndarray) -> np.ndarray:
        n_td = int(np.busday_count(today, self.expiry, holidays=NYSE_HOLIDAYS))
        n_cal = (self.expiry - today).days
        cp = "C" if self.opt_type is OptionType.CALL else "P"
        if n_td <= 0:
            raise ValueError(f"{self.ticker} {self.strike:g}{cp} {self.expiry.isoformat()} expired.")

        # integrity check
        try:
            assert v.shape[0] == ret.shape[0]
        except:
            raise ValueError("Price moves has a different length with vol moves.")

        multiplier = iv_multiplier(n_td, n_cal)

        price_today = bs_price(
            spot, 
            self.strike, 
            n_td / TRADING_DAYS,
            self.iv_quote * multiplier,
            self.opt_type,
            rate * multiplier ** 2
        )

        price_next_day = bs_price(
            spot * np.exp(ret),
            self.strike,
            (n_td - 1) / TRADING_DAYS,
            self.iv_quote * np.exp(v) * multiplier,
            self.opt_type,
            rate * multiplier ** 2
        )

        return (price_next_day - price_today) * self.qty * CONTRACT_MULTIPLIER * self.direction.value

    