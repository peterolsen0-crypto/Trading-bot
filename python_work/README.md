# Paper Trading Demo

A small learning project for experimenting with a moving-average crossover strategy using simulated prices.

## Try it in a browser

Open `docs/index.html` in a browser, or use GitHub Pages after deployment. The web demo runs entirely in the browser and does not call a trading service or send orders.

## Run the desktop demo

From PowerShell in this folder:

```powershell
pythonw .\trading_demo.py
```

The desktop app starts a simulated price stream. Its settings control the starting balance and price, moving-average windows, order size, fees, simulated volatility, and update interval. The historical sample button replays a fixed 90-price sequence.

## Run the console example

```powershell
python .\trading_bot.py
```

This prints a paper-trading example with sample prices, simulated fees, and a final result.

## Signal rules

- The fast moving average is computed from the latest completed prices in the shorter window.
- The slow moving average uses the longer window.
- A buy signal occurs when the fast average crosses above the slow average. The demo simulates a buy at the next price if there is no open position and enough cash.
- A sell signal occurs when the fast average crosses below the slow average. The demo simulates a sale at the next price when a position is open.
- The demo uses one long position at a time, charges a fee per order, and does not use leverage or short selling.

All prices are invented for demonstration. The program has no live market data, exchange connection, account credentials, or real order execution.

