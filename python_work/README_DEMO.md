# Paper Trading Lab — demo

A small desktop demo for learning how a moving-average crossover strategy works.

## Start it

From PowerShell in this folder, run:

```powershell
pythonw .\trading_demo.py
```

The demo starts in a live-running simulation and generates made-up prices locally. The update interval and simulated volatility are configurable. It has no exchange connection, API keys, live market data, or real order execution.

## What it shows

- Configurable starting balance and price, fast and slow moving-average windows, share size, fee rate, simulated volatility, and update interval.
- Buy and sell markers on a price chart.
- A cash result, return, number of completed rounds, fees, and a trade log.
- Start and stop controls for the live-running simulation, plus a historical sample run.
- Orders simulated at the next sample price after a crossover signal, with one position at a time and no leverage.

## Signals

- The fast moving average is the average of the most recent short window of completed prices.
- The slow moving average is the average of the most recent long window of completed prices.
- A buy signal occurs when the fast average crosses above the slow average. The demo buys at the next simulated price if it has no open position and enough cash.
- A sell signal occurs when the fast average crosses below the slow average. The demo sells at the next simulated price if it has an open position.
- A fee is charged on each simulated order. The demo does not short, use leverage, or place real orders.

The strategy is educational. Sample performance is not a forecast or investment recommendation.

