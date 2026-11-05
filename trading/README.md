# Paper-trading bot (Freqtrade)

[Freqtrade](https://github.com/freqtrade/freqtrade) is a free, open-source crypto trading bot
(GPL-3.0). This folder runs it in **paper-trading mode**: it watches real, live prices and makes
trades with **fake money** (a pretend wallet of 1,000 USDT). No exchange account and no money
are involved.

**Read this first.** A trading bot is not a money machine. Most people who run one lose money,
mostly to fees, strategies that only fit the past, and sudden market moves. Anyone selling
"guaranteed profit" bots is very likely scamming. Use this to learn how systematic trading
works, measure a strategy honestly, and build a quant project you can talk about. Don't use it
to get rich quickly.

## Run it (Windows)

Double-click `trading.cmd` in this folder and pick from the menu, or in PowerShell:

```
cd "$HOME\ai-office\trading"
.\trading.ps1 setup      # first time: installs Docker Desktop if needed, downloads price history
.\trading.ps1 backtest   # how the strategy did over the last year
.\trading.ps1 start      # paper trading, with the dashboard at http://127.0.0.1:8080
.\trading.ps1 stop
```

The first `setup` may install **Docker Desktop**: restart the computer, open Docker Desktop once,
then run `setup` again. macOS/Linux: `bash trading.sh setup | backtest | start | stop | status`.

The dashboard (FreqUI) shows open trades, profit, and a chart for each coin. Its password is in
`trading/.env`, which `setup` makes, and `start` prints it.

## What it trades

The bot runs **NostalgiaForInfinity X8**, the winner of the trading lab below, on 5-minute candles:
up to 6 trades at once sharing the 1,000 USDT pretend wallet, across 30 big coins. It buys dips in
many different ways and does not sell at a loss. It waits, and can buy more, until a trade
recovers, sometimes for weeks. The starter strategy below stays in the folder as an alternative.

### The starter strategy

- **Coins:** the same 30 coins against USDT (`pair_whitelist` in `user_data/config.json`), on
  hourly candles.
- **Strategy:** `user_data/strategies/TrendPullback.py`:
  - **When it buys:** only in an uptrend (price above the 200-hour average). It waits for a short
    dip that is turning back up (RSI back above 35).
  - **When it sells:** when the move is stretched (RSI above 75), or the trend breaks.
  - **Risk limits:** a 6% stop-loss and a trailing stop once a trade is 4% up. The config sets
    the rest: at most 6 trades at once, sharing the wallet.

## How to judge it

In the backtest:
- **Tot Profit %** is the result.
- **Max Drawdown** is the worst fall along the way.
- **Win%** is the share of trades that made money.
- **Market change** is what simply holding the coins would have done.

A strategy is only interesting if it beats holding after fees, with a drawdown you could live
through. It should also keep doing that in paper trading for weeks, on data it has never seen.
Change one thing at a time. `freqtrade hyperopt` can tune the two RSI levels, but heavy tuning
mostly fits noise.

## The trading lab: which strategy is actually best?

`trading/lab/` backtests many strategies under exactly the same conditions on real prices, and
ranks them honestly:
- **Data:** 30 big coins, two years. The first year checks each strategy; the second is data it
  has never been judged on.
- **Money:** a 1,000 USDT pretend wallet, up to 6 trades at once, the exchange's normal fees.
- **Strategies:** this folder's TrendPullback, plus the best-known open-source ones at fixed
  versions. These are [NostalgiaForInfinity](https://github.com/iterativv/NostalgiaForInfinity)
  X8, the most widely used community strategy, and 11 classics from
  [freqtrade-strategies](https://github.com/freqtrade/freqtrade-strategies).

A strategy **passes** only if it made money in both years, beat simply holding in at least one,
and its worst fall stayed under 35%. Ranking is by its weaker year, so one lucky year doesn't win.

It runs on GitHub's servers, not on your computer: in your repository, open **Actions → Trading
lab → Run workflow**. It takes one to a few hours. The ranked table appears on the run's page
(and as a download).

### Results of the first run (2 November 2026)

13 strategies, 30 coins, 2 years of real prices. "Worst fall" counts open trades at the market
price, hour by hour.

| Strategy | Year 1 | Year 2 (unseen) | Worst fall (year 1 / 2) | Note |
|---|---|---|---|---|
| NostalgiaForInfinity X8 | +102% (holding: +38%) | +31% (holding: −41%) | 35.4% / 26.4% | Best by far. Never sells at a loss: holds losing trades up to ~70 days. Misses the 35% limit by 0.4 points |
| CombinedBinHAndCluc | −29% | −8% | 58.7% / 21.2% | |
| TrendPullback (this folder) | −21% | −40% | 36.7% / 40.1% | |
| 10 other classics | −1% to −97% | | | Most lost heavily |

None passed every rule. NostalgiaForInfinity was the only one that made money in both years and
beat holding. Its price is that it sits through deep, long dips instead of cutting losses. Past
results don't promise future ones.

**The paper bot now runs NostalgiaForInfinity X8.** `setup`, `backtest` and `start` download the
exact version the lab tested (commit `c2e427d354131833ddacd1203b06166a959d30ad`) into
`user_data/strategies/`, and the config uses the conditions the lab tested. To go back to the
starter strategy, change `--strategy NostalgiaForInfinityX8` to `--strategy TrendPullback` in
`docker-compose.yml`.

## If you ever use real money

Don't, until paper trading has worked for at least a month. Then:
- Use an exchange that's legal for you (in Indonesia, one registered with OJK) and that Freqtrade
  supports.
- Create API keys with **trading only, no withdrawals**, and an IP restriction.
- Start with an amount you're fully prepared to lose.
- Set `"dry_run": false`, put the keys in `config.json` (never commit them), and keep
  `stake_amount` and `max_open_trades` small.

The bot does exactly what the strategy says, including losing money quickly in a crash.

## If the price download fails

Your network may block the exchange. In `user_data/config.json`, change `"name": "binance"` to
`"okx"` or `"kucoin"` and run `setup` again. Paper trading only needs public price data from it.
