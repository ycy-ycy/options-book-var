import json
from datetime import date
from pathlib import Path
from constants import CALENDAR_DAYS
from positions import Position, Stock, Option, Direction, Proxy, OptionType, iv_extraction

def _from_dict(d: dict, today: date, rate: float) -> Position:
    common = dict(
        ticker=d["ticker"],
        direction=Direction[d["direction"]],
        qty=float(d["qty"])
    )
    if d["type"] == "stock":
        return Stock(**common)
    if d["type"] == "option":
        for key in ("proxy", "price", "spot"):
            if key not in d:
                raise ValueError(f"{d['ticker']} {d['strike']} {d['opt_type']}: missing {key}")
        opt_type = OptionType[d["opt_type"]]
        strike = float(d["strike"])
        expiry = date.fromisoformat(d["expiry"])
        cp = "C" if opt_type is OptionType.CALL else "P"
        n_cal = (expiry - today).days
        if n_cal <= 0:
            raise ValueError(f"{d['ticker']} {strike:g}{cp} {expiry.isoformat()} expired as of {today.isoformat()}.")
        try:
            iv = iv_extraction(float(d["spot"]), strike, n_cal / CALENDAR_DAYS, float(d["price"]), opt_type, rate)
        except ValueError:
            raise ValueError(f"{d['ticker']} {strike:g}{cp} {expiry.isoformat()}: no IV fits "
                             f"price {d['price']} at spot {d['spot']}.") from None
        return Option(
            **common,
            proxy=Proxy[d["proxy"]],
            opt_type=opt_type,
            strike=strike,
            expiry=expiry,
            iv_quote=iv
        )
    raise ValueError(f"unknown position type: {d['type']!r}")

def load_positions(filename: str | Path) -> tuple[list[Position], date, float]:
    """JSON: {"today": "YYYY-MM-DD", "rate": r, "positions": [...]}; r is continuously compounded (from the
    US 1-year Treasury yield on "today"). Each option carries its premium "price" and the underlying "spot"
    as of "today". iv_quote is solved here, with calendar-day T and that rate."""
    with open(filename, encoding="utf-8") as f:
        doc = json.load(f)
    today = date.fromisoformat(doc["today"])
    rate = float(doc["rate"])
    return [_from_dict(d, today, rate) for d in doc["positions"]], today, rate

if __name__ == "__main__":
    positions, today, _ = load_positions("./positions.example.json")
    print(f"as of {today.isoformat()}")
    for position in positions:
        print(position)
