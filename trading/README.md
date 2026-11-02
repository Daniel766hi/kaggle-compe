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

- **Coins:** BTC, ETH, SOL, BNB, XRP against USDT, on hourly candles. Change them in
  `user_data/config.json` under `pair_whitelist`.
- **Strategy:** `user_data/strategies/TrendPullback.py`:
  - **When it buys:** only in an uptrend (price above the 200-hour average). It waits for a short
    dip that is turning back up (RSI back above 35).
  - **When it sells:** when the move is stretched (RSI above 75), or the trend breaks.
  - **Risk limits:** a 6% stop-loss, a trailing stop once a trade is 4% up, at most 3 trades at
    once, and 100 USDT each.

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
