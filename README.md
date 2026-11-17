# Options Book VaR

One-day VaR and ES for options books via (filtered) historical simulation with full Black-Scholes repricing.

## Quick start

```bash
pip install -r requirements.txt
python historical_simulation.py
```

This runs FHS (500-day window) on `positions.example.json` and shows the P&L histogram. Price and vol-index history is fetched from Yahoo Finance at run time, so a network connection is needed.

## Example

`positions.example.json`: 100 CBOE shares plus long calls on AMZN, META, MSFT, NVDA, TSM and GOOGL, marked at the 2026-11-06 close; rate 4.28% (US 1-year Treasury, continuously compounded).

> **Note on the as-of date.**
> 2026-11-06 is one trading day after a broad selloff
> (SPY −4.4% on 11/05; NVDA −9.7%, TSM −11.4%).
> That single day lifted the EWMA volatility of NVDA from 35% to 51%
> and of TSM from 39% to 58% (annualized),
> so FHS scales their whole history up accordingly.
> The HS / FHS gap below is partly that one shock.

One-day VaR99 / ES97.5 in dollars, 500-day window:

|        | HS    | FHS (EWMA, λ = 0.94) |
| ------ | ----- | -------------------- |
| VaR99  | 3,520 | 4,026                |
| ES97.5 | 3,536 | 4,162                |

Share of the book's ES97.5 by ticker:

| Ticker | HS    | FHS   |
| ------ | ----- | ----- |
| CBOE   | 30.3% | 19.6% |
| META   | 27.8% | 22.6% |
| AMZN   | 14.4% | 16.5% |
| MSFT   | 12.3% | 12.1% |
| NVDA   | 10.3% | 13.8% |
| TSM    | 5.6%  | 11.3% |
| GOOGL  | −0.7% | 4.2%  |

The standalone VaR99s add up to 6,507 (HS) and 9,083 (FHS), so diversification cuts the book's VaR by about 46% and 56%.

Yahoo rescales adjusted-close history whenever a dividend goes ex, so a rerun can differ from these figures by a few dollars even though the as-of date is fixed.

## Parameters

### Input file

A JSON object holding the as-of date, the rate and the legs of the book (see `positions.example.json`).

| Field       | Meaning                                                                                  |
| ----------- | ---------------------------------------------------------------------------------------- |
| `today`     | As-of date, `YYYY-MM-DD`: the close at which every quote in the file was taken.          |
| `rate`      | Risk-free rate, continuously compounded (the example uses the US 1-year Treasury yield). |
| `positions` | List of legs.                                                                            |

Each leg:

| Field       | Legs   | Meaning                                                                                                        |
| ----------- | ------ | -------------------------------------------------------------------------------------------------------------- |
| `type`      | all    | `stock` or `option`.                                                                                           |
| `ticker`    | all    | Yahoo Finance ticker of the underlying.                                                                        |
| `direction` | all    | `B` (long) or `S` (short).                                                                                     |
| `qty`       | all    | Shares for a stock, contracts for an option (100 shares each).                                                 |
| `proxy`     | option | Vol index whose daily log move shifts the leg's IV: `VIX9D`, `VIX`, `VIX3M`, `VXN9D`, `VXN`, `VXN3M`.          |
| `opt_type`  | option | `CALL` or `PUT`.                                                                                               |
| `strike`    | option | Strike.                                                                                                        |
| `expiry`    | option | Expiry date, `YYYY-MM-DD`.                                                                                     |
| `spot`      | option | Underlying close on `today`.                                                                                   |
| `price`     | option | Option premium per share on `today`. The IV is solved from `price`, `spot` and `rate` when the file is loaded. |

### Run arguments

`load_positions(file)` returns `(book, today, rate)`, which is passed on as `HS(book, today, rate, window=500, filtered=True, plot=True, bins=40)`.

| Argument   | Default | Meaning                                                                                                                                                                                                                                                                              |
| ---------- | ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `window`   | 500     | Number of scenarios. Scenario t is the set of moves from the close of trading day t − 1 to the close of day t, applied to the book as of `today`; the last scenario is the move into `today`. VaR99 is the (⌊0.01 · `window`⌋ + 1)-th worst scenario P&L, i.e. the 6th worst of 500. |
| `filtered` | `True`  | FHS: each stock's log return on day t is multiplied by σ_today / σ_t (EWMA, λ = 0.94), so past moves are restated at today's volatility. Vol-index moves are used as they are. Needs 112 days of history before the window.                                                          |
| `plot`     | `True`  | Show a histogram of the simulated one-day P&L of the book.                                                                                                                                                                                                                           |
| `bins`     | 40      | Number of histogram bins.                                                                                                                                                                                                                                                            |

## Methods

Each scenario reprices every leg in full under Black-Scholes; there is no delta / gamma approximation.

- **IV.** One IV per option, solved at load by inverting Black-Scholes (bisection) at the file's `spot`, `price` and `rate`.
- **Clock.** Each scenario advances one trading day, so theta is included. IV and rate are rescaled from calendar to trading-day time with total variance and discounting unchanged.
- **Spot move.** S · e^r, with r the log return of Yahoo's adjusted (total-return) closes; priced with q = 0.
- **Vol move.** IV · e^v, with v the log move of the leg's `proxy`: a parallel shift of the smile.
- **Synthetic proxies.** VXN9D / VXN3M = β · VXN log moves, with β the regression slope of VIX9D / VIX3M on VIX.
- **FHS.** Past stock moves are rescaled by σ_today / σ_t (EWMA, λ = 0.94); vol-index moves are not.
- **VaR / ES.** VaR99 is the (⌊0.01 · `window`⌋ + 1)-th worst scenario; ES97.5 averages the worst 2.5%, weighting the boundary scenario fractionally. A ticker's ES share is its average P&L over those same scenarios, so the shares add up to the book's ES.

## Limitations and status

Each method above is also a simplification:

1. **European pricing.** Listed equity options are American. Early exercise is ignored, which matters most for deep in-the-money puts and for calls before an ex-dividend date; short legs also carry assignment risk the model does not see.
2. **Vol dynamics.** Each option keeps its own IV, so today's smile is captured, but it does not respond to the spot move and its shape never changes. Errors grow with large moves and with strikes far from the money.
3. **Uniform time.** Variance and decay are spread evenly over trading days. A move across a weekend or an earnings date gets one ordinary day of decay, and event variance inside an IV is treated as diffusion (no post-event crush).
4. **Vol proxies.** A single name's IV is moved one-for-one with an index vol, which ignores its own vol beta and idiosyncratic events. The synthetic VXN9D / VXN3M also assume the Nasdaq term structure reacts like the S&P one, and β is fitted on the whole fetched history.
5. **Dividends.** Priced with q = 0, which slightly misprices options on dividend payers.
6. **FHS.** Rescaling applies to the whole move, so drift and one-off jumps on calm days (e.g. earnings) are inflated along with diffusion.
7. **Tail estimates.** VaR99 from 500 scenarios rests on the worst 5–6 of them.
8. **Data.** Yahoo Finance history is fetched at run time and adjusted closes are revised after every dividend. `NYSE_HOLIDAYS` runs only through 2028.

**Status:** the one-day HS / FHS engine is complete. Next: VaR backtesting (exception counts, Kupiec, Christoffersen, Basel traffic light).
