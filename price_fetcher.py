"""Yahoo daily adjclose: total return, consistent with q = 0 pricing."""
import json
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd

_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}?range={}&interval=1d"
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_close(ticker: str, rng: str = "2y") -> pd.Series:
    url = _URL.format(urllib.parse.quote(ticker), rng)
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            res = json.load(resp)["chart"]["result"][0]
    except Exception as e:
        raise RuntimeError(f"failed to fetch {ticker}") from e

    ts = np.asarray(res["timestamp"]) + res["meta"]["gmtoffset"]
    idx = pd.to_datetime(ts, unit="s").normalize()
    ind = res["indicators"]
    adj = ind.get("adjclose", [{}])[0].get("adjclose")
    s = pd.Series(adj if adj else ind["quote"][0]["close"], index=idx, dtype=float, name=ticker)
    return s[~s.index.duplicated(keep="last")].dropna()


def fetch_closes(tickers: list[str], rng: str = "2y") -> pd.DataFrame:
    px = pd.concat([fetch_close(t, rng) for t in tickers], axis=1)
    stocks = [t for t in tickers if not t.startswith("^")]
    # drop NYSE holidays (only ^ indices printed); other gaps: drop after taking returns
    return px.dropna(how="all", subset=stocks)


PROXY_TICKERS = ["^VIX9D", "^VIX", "^VIX3M", "^VXN"]


def proxy_moves(R: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """VXN9D / VXN3M = beta * v(^VXN), beta = slope of v(^VIX9D) / v(^VIX3M) on v(^VIX)."""
    V = R[PROXY_TICKERS].copy()
    betas = {}
    for name, ref in (("VXN9D", "^VIX9D"), ("VXN3M", "^VIX3M")):
        betas[name] = float(R[ref].cov(R["^VIX"]) / R["^VIX"].var())
        V[name] = betas[name] * R["^VXN"]
    return V, betas


def tbill_rate(irx: float, days: int = 91) -> float:
    """^IRX discount yield (%) -> continuous rate, ACT/365."""
    price = 1.0 - irx / 100.0 * days / 360.0
    return float(-np.log(price) / (days / 365.0))
