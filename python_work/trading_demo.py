"""A small, self-contained paper-trading demo. It never places real orders."""

from __future__ import annotations

import math
import random
import tkinter as tk
from statistics import mean
from tkinter import messagebox, ttk


BG = "#f3f6fb"
INK = "#172033"
MUTED = "#64748b"
BLUE = "#4f8cff"
TEAL = "#29c7ac"
ORANGE = "#f7a94b"
GREEN = "#38c986"
RED = "#ff6678"
CHART_BG = "#111827"


def make_demo_prices(start_price: float = 100.0) -> list[float]:
    """Return deterministic, invented prices for a repeatable demo."""
    values = []
    for day in range(90):
        trend = 100 + day * 0.11
        cycle = 8.5 * math.sin(day / 6.2) + 2.4 * math.sin(day / 1.85)
        values.append(round(start_price + trend - 100 + cycle, 2))
    return values


def moving_average(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for index in range(window - 1, len(values)):
        result[index] = mean(values[index - window + 1 : index + 1])
    return result


def simulate(
    prices: list[float], starting_cash: float, short_window: int,
    long_window: int, quantity: int, fee_percent: float,
) -> dict:
    short_average = moving_average(prices, short_window)
    long_average = moving_average(prices, long_window)
    fee_rate = fee_percent / 100
    cash = starting_cash
    position = 0
    fees_paid = 0.0
    events: list[dict] = []
    equity = [cash]

    # Use a completed bar for the signal and execute at the following sample price.
    for execution_index in range(1, len(prices)):
        signal_index = execution_index - 1
        if signal_index >= long_window:
            previous_short = short_average[signal_index - 1]
            previous_long = long_average[signal_index - 1]
            current_short = short_average[signal_index]
            current_long = long_average[signal_index]
            if None not in (previous_short, previous_long, current_short, current_long):
                crossed_up = previous_short <= previous_long and current_short > current_long
                crossed_down = previous_short >= previous_long and current_short < current_long
                price = prices[execution_index]

                if crossed_up and position == 0:
                    cost = price * quantity
                    fee = cost * fee_rate
                    if cash >= cost + fee:
                        cash -= cost + fee
                        position = quantity
                        fees_paid += fee
                        events.append({
                            "day": execution_index + 1, "side": "KJØP",
                            "price": price, "quantity": quantity,
                            "fee": fee, "cash": cash,
                        })
                elif crossed_down and position > 0:
                    proceeds = price * position
                    fee = proceeds * fee_rate
                    cash += proceeds - fee
                    fees_paid += fee
                    events.append({
                        "day": execution_index + 1, "side": "SALG",
                        "price": price, "quantity": position,
                        "fee": fee, "cash": cash,
                    })
                    position = 0

        equity.append(cash + position * prices[execution_index])

    # Close a remaining position at the last sample so ending cash is realized.
    if position:
        price = prices[-1]
        proceeds = price * position
        fee = proceeds * fee_rate
        cash += proceeds - fee
        fees_paid += fee
        events.append({
            "day": len(prices), "side": "SALG (slutt)",
            "price": price, "quantity": position,
            "fee": fee, "cash": cash,
        })
        position = 0
        equity[-1] = cash

    return {
        "prices": prices,
        "short_average": short_average,
        "long_average": long_average,
        "equity": equity,
        "events": events,
        "starting_cash": starting_cash,
        "ending_cash": cash,
        "return_value": cash - starting_cash,
        "return_percent": (cash / starting_cash - 1) * 100,
        "fees_paid": fees_paid,
        "round_trips": sum(event["side"].startswith("SALG") for event in events),
    }


class TradingDemo:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Paper Trading Lab | Demo")
        self.root.geometry("1240x820")
        self.root.minsize(1000, 700)
        self.root.configure(background=BG)

        self.start_cash = tk.StringVar(value="10000")
        self.start_price = tk.StringVar(value="100")
        self.short_window = tk.StringVar(value="5")
        self.long_window = tk.StringVar(value="14")
        self.quantity = tk.StringVar(value="10")
        self.fee_percent = tk.StringVar(value="0.1")
        self.volatility_percent = tk.StringVar(value="0.8")
        self.update_interval = tk.StringVar(value="1000")
        self.result: dict | None = None
        self.live_active = False
        self.live_job: str | None = None
        self.live_data: dict | None = None

        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"), foreground="white", background="#17243b")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#c5d0e2", background="#17243b")
        style.configure("Card.TLabelframe", background="white", bordercolor="#e0e7f0")
        style.configure("Card.TLabelframe.Label", background="white", foreground=INK, font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=27, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(12, 8))

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.start_live_demo()

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, background="#17243b", padx=24, pady=17)
        header.pack(fill="x")
        ttk.Label(header, text="Paper Trading Lab", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Fortløpende simulering av syntetiske kurser · ingen ekte ordre eller konto-tilkobling",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        content = ttk.Frame(self.root, padding=(18, 16))
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(1, weight=1)

        controls_box = ttk.LabelFrame(content, text="Demo-innstillinger", style="Card.TLabelframe", padding=6)
        controls_box.grid(row=0, column=0, rowspan=4, sticky="nsew", padx=(0, 14))
        controls_box.columnconfigure(0, weight=1)
        controls_box.rowconfigure(0, weight=1)
        controls_canvas = tk.Canvas(controls_box, background="white", highlightthickness=0, width=285)
        controls_scrollbar = ttk.Scrollbar(controls_box, orient="vertical", command=controls_canvas.yview)
        controls_canvas.configure(yscrollcommand=controls_scrollbar.set)
        controls_canvas.grid(row=0, column=0, sticky="nsew")
        controls_scrollbar.grid(row=0, column=1, sticky="ns")
        controls = ttk.Frame(controls_canvas, padding=10)
        controls_window = controls_canvas.create_window((0, 0), window=controls, anchor="nw")
        controls.bind(
            "<Configure>",
            lambda _event: controls_canvas.configure(scrollregion=controls_canvas.bbox("all")),
        )
        controls_canvas.bind(
            "<Configure>",
            lambda event: controls_canvas.itemconfigure(controls_window, width=event.width),
        )
        controls.columnconfigure(0, weight=1)

        self._field(controls, 0, "Startkapital ($)", self.start_cash)
        self._field(controls, 1, "Startkurs ($)", self.start_price)
        self._field(controls, 2, "Raskt gjennomsnitt (priser)", self.short_window)
        self._field(controls, 3, "Langt gjennomsnitt (priser)", self.long_window)
        self._field(controls, 4, "Aksjer per handel", self.quantity)
        self._field(controls, 5, "Gebyr per handel (%)", self.fee_percent)
        self._field(controls, 6, "Simulert volatilitet (%)", self.volatility_percent)
        self._field(controls, 7, "Oppdatering (millisekunder)", self.update_interval)

        ttk.Label(controls, text="Strategi", font=("Segoe UI", 10, "bold")).grid(
            row=16, column=0, sticky="w", pady=(18, 4)
        )
        ttk.Label(
            controls,
            text=(
                "RASKT snitt = gjennomsnittet av de siste korte prisene. LANGT snitt = gjennomsnittet av de siste lange prisene.\n\n"
                "KJØP: raskt snitt krysser opp over langt snitt.\n"
                "SELG: raskt snitt krysser ned under langt snitt.\n\n"
                "Signaler beregnes fra ferdige priser og utføres ved neste oppdatering. Botten holder maksimalt én kjøpsposisjon, uten shorting eller belåning."
            ),
            wraplength=255,
            justify="left",
        ).grid(row=17, column=0, sticky="w")

        ttk.Button(controls, text="Start live-demo", style="Accent.TButton", command=self.start_live_demo).grid(
            row=18, column=0, sticky="ew", pady=(16, 7)
        )
        ttk.Button(controls, text="Stopp live-demo", command=self.stop_live_demo).grid(
            row=19, column=0, sticky="ew", pady=(0, 7)
        )
        ttk.Button(controls, text="Kjør historisk eksempel", command=self.run_demo).grid(
            row=20, column=0, sticky="ew", pady=(0, 7)
        )
        ttk.Button(controls, text="Tilbakestill innstillinger", command=self.reset).grid(
            row=21, column=0, sticky="ew"
        )
        ttk.Label(
            controls,
            text="Etter at du endrer feltene, trykk Start live-demo eller Kjør historisk eksempel for å bruke de nye verdiene.",
            wraplength=255,
            justify="left",
            foreground=MUTED,
        ).grid(row=22, column=0, sticky="w", pady=(12, 0))
        ttk.Label(
            controls,
            text="Dataene er oppdiktede og laget for demonstrasjon. Resultatet sier ikke noe om fremtidig avkastning.",
            wraplength=220,
            justify="left",
            foreground=MUTED,
        ).grid(row=23, column=0, sticky="w", pady=(14, 0))

        metrics = ttk.Frame(content)
        metrics.grid(row=0, column=1, sticky="ew", pady=(0, 12))
        for index in range(4):
            metrics.columnconfigure(index, weight=1)
        self.metric_values: list[ttk.Label] = []
        for index, title in enumerate(("STARTKAPITAL", "PORTEFØLJEVERDI", "RESULTAT", "RUNDER")):
            card = tk.Frame(metrics, background="white", highlightbackground="#e0e7f0", highlightthickness=1, padx=13, pady=10)
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 8, 0))
            tk.Label(card, text=title, background="white", foreground=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
            value = tk.Label(card, text="—", background="white", foreground=INK, font=("Segoe UI", 15, "bold"))
            value.pack(anchor="w", pady=(5, 0))
            self.metric_values.append(value)

        chart_frame = ttk.LabelFrame(content, text="Pris og glidende gjennomsnitt", style="Card.TLabelframe", padding=8)
        chart_frame.grid(row=1, column=1, sticky="nsew", pady=(0, 12))
        chart_frame.rowconfigure(0, weight=1)
        chart_frame.columnconfigure(0, weight=1)
        self.chart = tk.Canvas(chart_frame, background=CHART_BG, height=330, highlightthickness=0)
        self.chart.grid(row=0, column=0, sticky="nsew")
        self.chart.bind("<Configure>", self._draw_chart)

        bottom = ttk.LabelFrame(content, text="Handelslogg", style="Card.TLabelframe", padding=8)
        bottom.grid(row=2, column=1, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        columns = ("day", "side", "price", "quantity", "fee", "cash")
        self.log = ttk.Treeview(bottom, columns=columns, show="headings", height=5)
        headings = {
            "day": ("Dag", 65), "side": ("Handling", 115),
            "price": ("Pris", 100), "quantity": ("Antall", 80),
            "fee": ("Gebyr", 95), "cash": ("Kontanter etterpå", 150),
        }
        for column, (label, width) in headings.items():
            self.log.heading(column, text=label)
            self.log.column(column, width=width, anchor="center")
        scrollbar = ttk.Scrollbar(bottom, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="ew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.status = ttk.Label(content, text="Klar", foreground=MUTED)
        self.status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(9, 0))

    @staticmethod
    def _field(parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row * 2, column=0, sticky="w", pady=(8, 2))
        ttk.Entry(parent, textvariable=variable, width=24).grid(row=row * 2 + 1, column=0, sticky="ew")

    def reset(self) -> None:
        self.start_cash.set("10000")
        self.start_price.set("100")
        self.short_window.set("5")
        self.long_window.set("14")
        self.quantity.set("10")
        self.fee_percent.set("0.1")
        self.volatility_percent.set("0.8")
        self.update_interval.set("1000")
        self.start_live_demo()

    def _read_settings(self) -> tuple[float, float, int, int, int, float, float, int] | None:
        try:
            start_cash = float(self.start_cash.get())
            start_price = float(self.start_price.get())
            short_window = int(self.short_window.get())
            long_window = int(self.long_window.get())
            quantity = int(self.quantity.get())
            fee_percent = float(self.fee_percent.get())
            volatility_percent = float(self.volatility_percent.get())
            update_interval = int(self.update_interval.get())
            if start_cash <= 0 or start_price <= 0 or quantity <= 0:
                raise ValueError("Startkapital, startkurs og antall aksjer må være større enn null.")
            if short_window < 2 or long_window <= short_window or long_window >= 90:
                raise ValueError("Bruk 2 ≤ raskt snitt < langt snitt < 90.")
            if fee_percent < 0 or fee_percent > 10:
                raise ValueError("Gebyr må være mellom 0 og 10 prosent.")
            if volatility_percent < 0 or volatility_percent > 10:
                raise ValueError("Volatilitet må være mellom 0 og 10 prosent.")
            if update_interval < 100 or update_interval > 10000:
                raise ValueError("Oppdateringshastighet må være mellom 100 og 10 000 millisekunder.")
        except ValueError as error:
            messagebox.showerror("Ugyldige innstillinger", str(error), parent=self.root)
            return None
        return (
            start_cash, start_price, short_window, long_window, quantity,
            fee_percent, volatility_percent, update_interval,
        )

    def run_demo(self) -> None:
        settings = self._read_settings()
        if settings is None:
            return
        self._cancel_live_timer()
        self.live_active = False
        self.live_data = None
        start_cash, start_price, short_window, long_window, quantity, fee_percent, _, _ = settings

        prices = make_demo_prices(start_price)
        self.result = simulate(prices, start_cash, short_window, long_window, quantity, fee_percent)
        self.status.configure(text="Historisk demo · oppdiktede priser · ingen ekte ordre")
        self._refresh_result()

    def _refresh_result(self) -> None:
        if self.result is None:
            return
        result = self.result
        self.metric_values[0].configure(text=f"${result['starting_cash']:,.2f}")
        self.metric_values[1].configure(text=f"${result['ending_cash']:,.2f}")
        self.metric_values[2].configure(
            text=f"${result['return_value']:+,.2f}  ({result['return_percent']:+.2f}%)",
            foreground=GREEN if result["return_value"] >= 0 else RED,
        )
        self.metric_values[3].configure(text=str(result["round_trips"]))

        for row in self.log.get_children():
            self.log.delete(row)
        for event in result["events"]:
            self.log.insert("", "end", values=(
                event["day"], event["side"], f"${event['price']:.2f}",
                event["quantity"], f"${event['fee']:.2f}", f"${event['cash']:,.2f}",
            ))
        self._draw_chart()

    def start_live_demo(self) -> None:
        settings = self._read_settings()
        if settings is None:
            return
        (
            start_cash, start_price, short_window, long_window, quantity,
            fee_percent, volatility_percent, update_interval,
        ) = settings
        self._cancel_live_timer()
        self.live_active = True
        self.live_data = {
            "starting_cash": start_cash,
            "cash": start_cash,
            "position": 0,
            "short_window": short_window,
            "long_window": long_window,
            "quantity": quantity,
            "fee_rate": fee_percent / 100,
            "volatility_percent": volatility_percent,
            "update_interval": update_interval,
            "fees_paid": 0.0,
            "prices": [start_price],
            "equity": [start_cash],
            "events": [],
            "tick": 1,
            "rng": random.Random(),
        }
        self.status.configure(text="LIVE-DEMO · oppdiktede priser · starter …")
        self._live_tick()

    def _live_tick(self) -> None:
        data = self.live_data
        if not self.live_active or data is None:
            return

        data["tick"] += 1
        amplitude = data["prices"][-1] * data["volatility_percent"] / 100
        movement = 0.02 + amplitude * (0.45 * math.sin(data["tick"] / 7) + data["rng"].uniform(-1, 1))
        price = max(20.0, round(data["prices"][-1] + movement, 2))
        data["prices"].append(price)

        if len(data["prices"]) > 180:
            data["prices"].pop(0)
            data["equity"].pop(0)
            for event in data["events"]:
                event["chart_index"] -= 1
            data["events"] = [event for event in data["events"] if event["chart_index"] >= 0]

        signal_index = len(data["prices"]) - 2
        short_window = data["short_window"]
        long_window = data["long_window"]
        short_average = moving_average(data["prices"], short_window)
        long_average = moving_average(data["prices"], long_window)
        if signal_index >= long_window:
            previous_short = short_average[signal_index - 1]
            previous_long = long_average[signal_index - 1]
            current_short = short_average[signal_index]
            current_long = long_average[signal_index]
            if None not in (previous_short, previous_long, current_short, current_long):
                crossed_up = previous_short <= previous_long and current_short > current_long
                crossed_down = previous_short >= previous_long and current_short < current_long
                if crossed_up and data["position"] == 0:
                    cost = price * data["quantity"]
                    fee = cost * data["fee_rate"]
                    if data["cash"] >= cost + fee:
                        data["cash"] -= cost + fee
                        data["position"] = data["quantity"]
                        data["fees_paid"] += fee
                        data["events"].append(self._live_event(data, "KJØP", price, fee))
                elif crossed_down and data["position"] > 0:
                    proceeds = price * data["position"]
                    fee = proceeds * data["fee_rate"]
                    data["cash"] += proceeds - fee
                    data["fees_paid"] += fee
                    data["events"].append(self._live_event(data, "SALG", price, fee))
                    data["position"] = 0

        portfolio_value = data["cash"] + data["position"] * price
        data["equity"].append(portfolio_value)
        if len(data["events"]) > 100:
            data["events"] = data["events"][-100:]
        self.result = {
            "prices": data["prices"],
            "short_average": short_average,
            "long_average": long_average,
            "equity": data["equity"],
            "events": data["events"],
            "starting_cash": data["starting_cash"],
            "ending_cash": portfolio_value,
            "return_value": portfolio_value - data["starting_cash"],
            "return_percent": (portfolio_value / data["starting_cash"] - 1) * 100,
            "fees_paid": data["fees_paid"],
            "round_trips": sum(event["side"].startswith("SALG") for event in data["events"]),
        }
        self.status.configure(
            text=f"LIVE-DEMO · dag {data['tick']} · syntetiske priser · gebyrer: ${data['fees_paid']:.2f}"
        )
        self._refresh_result()
        self.live_job = self.root.after(data["update_interval"], self._live_tick)

    @staticmethod
    def _live_event(data: dict, side: str, price: float, fee: float) -> dict:
        return {
            "day": data["tick"],
            "chart_index": len(data["prices"]) - 1,
            "side": side,
            "price": price,
            "quantity": data["quantity"],
            "fee": fee,
            "cash": data["cash"],
        }

    def stop_live_demo(self) -> None:
        self.live_active = False
        self._cancel_live_timer()
        self.status.configure(text="Live-demo pauset · porteføljen er fortsatt simulert")

    def _cancel_live_timer(self) -> None:
        if self.live_job is not None:
            try:
                self.root.after_cancel(self.live_job)
            except tk.TclError:
                pass
            self.live_job = None

    def close(self) -> None:
        self.live_active = False
        self._cancel_live_timer()
        self.root.destroy()

    def _draw_chart(self, _event=None) -> None:
        if not self.result:
            return
        canvas = self.chart
        canvas.delete("all")
        width = max(canvas.winfo_width(), 500)
        height = max(canvas.winfo_height(), 280)
        left, right, top, bottom = 62, 18, 38, 34
        plot_width = width - left - right
        plot_height = height - top - bottom

        series = self.result["prices"]
        short_average = self.result["short_average"]
        long_average = self.result["long_average"]
        all_values = series + [value for value in short_average + long_average if value is not None]
        low, high = min(all_values), max(all_values)
        padding = max((high - low) * 0.1, 1)
        low -= padding
        high += padding

        def x(index: int) -> float:
            return left + index * plot_width / (len(series) - 1)

        def y(value: float) -> float:
            return top + (high - value) * plot_height / (high - low)

        for step in range(5):
            value = low + (high - low) * step / 4
            yy = y(value)
            canvas.create_line(left, yy, width - right, yy, fill="#273449")
            canvas.create_text(left - 8, yy, text=f"${value:.0f}", fill="#aebbd0", anchor="e", font=("Segoe UI", 8))

        def draw_series(values: list[float | None], color: str, line_width: int) -> None:
            points = [(x(index), y(value)) for index, value in enumerate(values) if value is not None]
            if len(points) >= 2:
                canvas.create_line(*[coordinate for point in points for coordinate in point], fill=color, width=line_width, smooth=True)

        draw_series(series, BLUE, 2)
        draw_series(short_average, TEAL, 2)
        draw_series(long_average, ORANGE, 2)

        for event in self.result["events"]:
            index = min(event.get("chart_index", event["day"] - 1), len(series) - 1)
            if index < 0:
                continue
            px, py = x(index), y(series[index])
            if event["side"].startswith("KJØP"):
                canvas.create_polygon(px, py - 10, px - 6, py + 1, px + 6, py + 1, fill=GREEN, outline="white")
            else:
                canvas.create_polygon(px, py + 10, px - 6, py - 1, px + 6, py - 1, fill=RED, outline="white")

        canvas.create_text(left, 15, text="Pris", fill=BLUE, anchor="w", font=("Segoe UI", 9, "bold"))
        canvas.create_line(left + 33, 15, left + 55, 15, fill=BLUE, width=2)
        canvas.create_text(left + 70, 15, text="Raskt snitt", fill=TEAL, anchor="w", font=("Segoe UI", 9, "bold"))
        canvas.create_line(left + 145, 15, left + 167, 15, fill=TEAL, width=2)
        canvas.create_text(left + 182, 15, text="Langt snitt", fill=ORANGE, anchor="w", font=("Segoe UI", 9, "bold"))
        canvas.create_line(left + 260, 15, left + 282, 15, fill=ORANGE, width=2)
        canvas.create_text(left + 295, 15, text="Kjøp", fill=GREEN, anchor="w", font=("Segoe UI", 9, "bold"))
        canvas.create_polygon(left + 326, 15, left + 320, 9, left + 332, 9, fill=GREEN)
        canvas.create_text(left + 350, 15, text="Salg", fill=RED, anchor="w", font=("Segoe UI", 9, "bold"))
        canvas.create_polygon(left + 380, 15, left + 374, 21, left + 386, 21, fill=RED)


if __name__ == "__main__":
    app_root = tk.Tk()
    TradingDemo(app_root)
    app_root.mainloop()

