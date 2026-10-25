# Trading Bot + Paper Demo

This repository contains two separate parts:

- `docs/` is a static, browser-only paper-trading demo. GitHub Pages publishes only this folder. It uses made-up prices and does not make network requests, connect to an exchange, or place orders.
- `python_work/` contains the beginner Python exercises, console simulation, and Tkinter paper-trading demo.
- `server.py` and `dashboard/` are a separate Capital.com bridge and account dashboard. The bridge can send broker orders when configured with credentials. It is not used by GitHub Pages.

## Try the browser demo

When Pages deployment is enabled, visit:

`https://peterolsen0-crypto.github.io/Trading-bot/`

The page starts a synthetic price simulation automatically. Visitors can change the starting cash and price, moving-average windows, share size, fee, simulated volatility, and update speed. They can pause the simulation or run a fixed 90-price sample.

## Run the Python desktop demo

From the `python_work` folder on Windows:

```powershell
pythonw .\trading_demo.py
```

All prices in the demo are invented for learning. Demo results are not forecasts or investment advice.

