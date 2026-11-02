"""TrendPullback: a simple, explainable starter strategy for paper trading.

Idea: only buy in an uptrend, and only after a short dip that is already recovering.
  - Trend: price above the 200-hour EMA, and the 50-hour EMA above the 200-hour EMA.
  - Entry: RSI(14) climbs back above 35 (a pullback that is turning up), on real volume.
  - Exit: RSI above 75 (stretched), or price falls clearly below the 200-hour EMA (trend broken).
  - Risk: a -6% stop-loss, a trailing stop once a trade is +4% up, and profit targets that
    get smaller the longer a trade is open.

This is a starting point to learn from, not a money machine. Backtest it, paper trade it, and
change one thing at a time. Results on past data do not promise future results.
"""

import talib.abstract as ta
from pandas import DataFrame

from freqtrade.strategy import IStrategy, IntParameter
from technical import qtpylib


class TrendPullback(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "1h"
    can_short = False

    # Take profit: 10% at once, 5% after 12 hours, 2% after a day.
    minimal_roi = {"0": 0.10, "720": 0.05, "1440": 0.02}
    stoploss = -0.06
    trailing_stop = True
    trailing_stop_positive = 0.02
    trailing_stop_positive_offset = 0.04
    trailing_only_offset_is_reached = True

    process_only_new_candles = True
    startup_candle_count = 210  # the 200-hour EMA needs history first

    # Tunable with `freqtrade hyperopt` (keep the ranges narrow to avoid fitting noise).
    rsi_entry = IntParameter(25, 45, default=35, space="buy")
    rsi_exit = IntParameter(65, 85, default=75, space="sell")

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        uptrend = (dataframe["close"] > dataframe["ema200"]) & (dataframe["ema50"] > dataframe["ema200"])
        recovering = qtpylib.crossed_above(dataframe["rsi"], self.rsi_entry.value)
        dataframe.loc[uptrend & recovering & (dataframe["volume"] > 0), ["enter_long", "enter_tag"]] = (1, "pullback")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        stretched = dataframe["rsi"] > self.rsi_exit.value
        broken = dataframe["close"] < dataframe["ema200"] * 0.98
        dataframe.loc[stretched & (dataframe["volume"] > 0), ["exit_long", "exit_tag"]] = (1, "rsi_high")
        dataframe.loc[broken & (dataframe["volume"] > 0), ["exit_long", "exit_tag"]] = (1, "trend_broken")
        return dataframe
