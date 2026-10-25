"""Educational paper-trading example using synthetic prices only."""

from statistics import mean


# These are made-up sample prices, not live or historical market data.
prices = [
    100, 99, 98, 97, 96, 97, 99, 102, 105, 108, 110,
    108, 105, 102, 100, 98, 96, 98, 101, 104, 108,
    112, 115, 113, 110, 107, 104, 102, 105, 109, 113,
]

starting_cash = 10_000.00
shares_per_trade = 10
fee_rate = 0.001  # 0.1% per simulated trade
short_window = 3
long_window = 5


def main():
    cash = starting_cash
    shares = 0
    fees_paid = 0.0
    trades = 0

    print("PAPER TRADING DEMO - synthetic sample prices")
    print("Strategy: 3-day / 5-day moving-average crossover")
    print("No live data and no real orders.\n")
    print(f"Starting cash: ${cash:,.2f}")
    print(f"Trade size: {shares_per_trade} shares | Simulated fee: {fee_rate:.1%}\n")

    for index in range(long_window + 1, len(prices)):
        # Decide using yesterday's completed prices; simulate the trade today.
        signal_index = index - 1
        short_average = mean(prices[signal_index - short_window + 1 : signal_index + 1])
        long_average = mean(prices[signal_index - long_window + 1 : signal_index + 1])
        action = ""

        previous_short = mean(prices[signal_index - short_window : signal_index])
        previous_long = mean(prices[signal_index - long_window : signal_index])
        crossed_up = previous_short <= previous_long and short_average > long_average
        crossed_down = previous_short >= previous_long and short_average < long_average

        if crossed_up and shares == 0:
            cost = prices[index] * shares_per_trade
            fee = cost * fee_rate
            if cash >= cost + fee:
                cash -= cost + fee
                shares = shares_per_trade
                fees_paid += fee
                trades += 1
                action = f"BUY {shares} @ ${prices[index]:.2f} (fee ${fee:.2f})"

        elif crossed_down and shares > 0:
            proceeds = prices[index] * shares
            fee = proceeds * fee_rate
            cash += proceeds - fee
            fees_paid += fee
            trades += 1
            action = f"SELL {shares} @ ${prices[index]:.2f} (fee ${fee:.2f})"
            shares = 0

        if action:
            print(f"Day {index + 1:02d} | price ${prices[index]:6.2f} | {action}")

    # Close any open simulated position at the final sample price.
    if shares:
        proceeds = prices[-1] * shares
        fee = proceeds * fee_rate
        cash += proceeds - fee
        fees_paid += fee
        trades += 1
        print(f"Final day | price ${prices[-1]:6.2f} | SELL {shares} @ ${prices[-1]:.2f} (fee ${fee:.2f})")
        shares = 0

    profit_loss = cash - starting_cash
    print("\nSIMULATION SUMMARY")
    print(f"Ending cash:  ${cash:,.2f}")
    print(f"Profit/loss:  ${profit_loss:,.2f} ({profit_loss / starting_cash:.2%})")
    print(f"Trades:       {trades}")
    print(f"Fees paid:    ${fees_paid:.2f}")
    print("\nThis result uses invented prices and is not a prediction or recommendation.")


if __name__ == "__main__":
    main()

