const $ = (id) => document.getElementById(id);
const DEFAULTS = {
  startingCash: 10000,
  startingPrice: 100,
  fastWindow: 5,
  slowWindow: 14,
  quantity: 10,
  feePercent: 0.1,
  volatility: 0.8,
  interval: 1000,
};

let appState = null;

const round2 = (value) => Math.round((value + Number.EPSILON) * 100) / 100;
const money = (value) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);

function readSettings() {
  const values = {};
  for (const key of Object.keys(DEFAULTS)) values[key] = Number($(key).value);
  const fast = $("fastWindow");
  const slow = $("slowWindow");
  fast.setCustomValidity("");
  slow.setCustomValidity("");
  if (values.fastWindow >= values.slowWindow) {
    slow.setCustomValidity("Det lange snittet må være større enn det raske.");
    slow.reportValidity();
    return null;
  }
  if (!$("settingsForm").reportValidity()) return null;
  return values;
}

function smaAt(prices, window, index) {
  if (index < window - 1) return null;
  let sum = 0;
  for (let i = index - window + 1; i <= index; i++) sum += prices[i];
  return sum / window;
}

function movingAverages(prices, window) {
  return prices.map((_price, index) => smaAt(prices, window, index));
}

function makeRandom(seed) {
  let value = seed >>> 0;
  return () => {
    value += 0x6d2b79f5;
    let next = value;
    next = Math.imul(next ^ (next >>> 15), next | 1);
    next ^= next + Math.imul(next ^ (next >>> 7), next | 61);
    return ((next ^ (next >>> 14)) >>> 0) / 4294967296;
  };
}

function createLiveState(settings) {
  return {
    mode: "live",
    active: true,
    settings,
    prices: [round2(settings.startingPrice)],
    equity: [settings.startingCash],
    cash: settings.startingCash,
    position: 0,
    fees: 0,
    day: 1,
    totalOrders: 0,
    events: [],
    random: makeRandom((Date.now() ^ Math.floor(Math.random() * 0xffffffff)) >>> 0),
    timer: null,
  };
}

function recordOrder(state, side, price, fee) {
  state.events.push({
    day: state.day,
    chartIndex: state.prices.length - 1,
    side,
    price,
    quantity: state.settings.quantity,
    fee,
    cash: state.cash,
  });
  state.totalOrders++;
}

function executeSignal(state, price, crossedUp, crossedDown) {
  const settings = state.settings;
  const rate = settings.feePercent / 100;
  if (crossedUp && state.position === 0) {
    const value = price * settings.quantity;
    const fee = round2(value * rate);
    if (state.cash >= value + fee) {
      state.cash = round2(state.cash - value - fee);
      state.position = settings.quantity;
      state.fees = round2(state.fees + fee);
      recordOrder(state, "KJØP", price, fee);
    }
  } else if (crossedDown && state.position > 0) {
    const value = price * state.position;
    const fee = round2(value * rate);
    state.cash = round2(state.cash + value - fee);
    state.fees = round2(state.fees + fee);
    recordOrder(state, "SALG", price, fee);
    state.position = 0;
  }
}

function liveTick() {
  const state = appState;
  if (!state || state.mode !== "live" || !state.active) return;
  const settings = state.settings;
  const previousPrice = state.prices[state.prices.length - 1];
  state.day++;
  const amplitude = previousPrice * settings.volatility / 100;
  const wave = 0.45 * Math.sin(state.day / 7) + (state.random() * 2 - 1);
  const price = round2(Math.max(1, previousPrice + 0.02 + amplitude * wave));
  state.prices.push(price);

  if (state.prices.length > 180) {
    state.prices.shift();
    state.equity.shift();
    for (const event of state.events) event.chartIndex--;
    state.events = state.events.filter((event) => event.chartIndex >= 0);
  }

  const signalIndex = state.prices.length - 2;
  const fastNow = smaAt(state.prices, settings.fastWindow, signalIndex);
  const slowNow = smaAt(state.prices, settings.slowWindow, signalIndex);
  const fastBefore = smaAt(state.prices, settings.fastWindow, signalIndex - 1);
  const slowBefore = smaAt(state.prices, settings.slowWindow, signalIndex - 1);
  if ([fastNow, slowNow, fastBefore, slowBefore].every((item) => item !== null)) {
    const crossedUp = fastBefore <= slowBefore && fastNow > slowNow;
    const crossedDown = fastBefore >= slowBefore && fastNow < slowNow;
    executeSignal(state, price, crossedUp, crossedDown);
  }

  state.equity.push(round2(state.cash + state.position * price));
  if (state.events.length > 100) state.events = state.events.slice(-100);
  render();
  state.timer = window.setTimeout(liveTick, settings.interval);
}

function startLive() {
  const settings = readSettings();
  if (!settings) return;
  pauseLive();
  appState = createLiveState(settings);
  setStatus(true, "Live simulering");
  render();
  liveTick();
}

function pauseLive() {
  if (!appState) return;
  if (appState.timer) window.clearTimeout(appState.timer);
  appState.timer = null;
  if (appState.mode === "live") {
    appState.active = false;
    setStatus(false, "Pauset");
  }
}

function makeHistoricalPrices(startPrice) {
  return Array.from({ length: 90 }, (_item, day) => {
    const trend = day * 0.11;
    const cycle = 8.5 * Math.sin(day / 6.2) + 2.4 * Math.sin(day / 1.85);
    return round2(Math.max(1, startPrice + trend + cycle));
  });
}

function runHistorical() {
  const settings = readSettings();
  if (!settings) return;
  pauseLive();
  const prices = makeHistoricalPrices(settings.startingPrice);
  const events = [];
  let cash = settings.startingCash;
  let position = 0;
  let fees = 0;
  let totalOrders = 0;
  const equity = [cash];
  const rate = settings.feePercent / 100;

  for (let executionIndex = 1; executionIndex < prices.length; executionIndex++) {
    const signalIndex = executionIndex - 1;
    if (signalIndex >= settings.slowWindow) {
      const fastNow = smaAt(prices, settings.fastWindow, signalIndex);
      const slowNow = smaAt(prices, settings.slowWindow, signalIndex);
      const fastBefore = smaAt(prices, settings.fastWindow, signalIndex - 1);
      const slowBefore = smaAt(prices, settings.slowWindow, signalIndex - 1);
      if ([fastNow, slowNow, fastBefore, slowBefore].every((item) => item !== null)) {
        const crossedUp = fastBefore <= slowBefore && fastNow > slowNow;
        const crossedDown = fastBefore >= slowBefore && fastNow < slowNow;
        const price = prices[executionIndex];
        if (crossedUp && position === 0) {
          const value = price * settings.quantity;
          const fee = round2(value * rate);
          if (cash >= value + fee) {
            cash = round2(cash - value - fee);
            position = settings.quantity;
            fees = round2(fees + fee);
            totalOrders++;
            events.push({ day: executionIndex + 1, chartIndex: executionIndex, side: "KJØP", price, quantity: position, fee, cash });
          }
        } else if (crossedDown && position > 0) {
          const value = price * position;
          const fee = round2(value * rate);
          cash = round2(cash + value - fee);
          fees = round2(fees + fee);
          totalOrders++;
          events.push({ day: executionIndex + 1, chartIndex: executionIndex, side: "SALG", price, quantity: position, fee, cash });
          position = 0;
        }
      }
    }
    equity.push(round2(cash + position * prices[executionIndex]));
  }

  if (position > 0) {
    const price = prices[prices.length - 1];
    const fee = round2(price * position * rate);
    cash = round2(cash + price * position - fee);
    fees = round2(fees + fee);
    totalOrders++;
    events.push({ day: prices.length, chartIndex: prices.length - 1, side: "SALG (slutt)", price, quantity: position, fee, cash });
    equity[equity.length - 1] = cash;
  }

  appState = {
    mode: "history", active: false, settings, prices, equity, cash,
    position: 0, fees, events, totalOrders, timer: null,
  };
  setStatus(false, "Historisk eksempel");
  render();
}

function setStatus(isLive, text) {
  $("statusText").textContent = text;
  $("statusDot").classList.toggle("paused", !isLive);
}

function render() {
  const state = appState;
  if (!state || state.prices.length === 0) return;
  const price = state.prices[state.prices.length - 1];
  const portfolio = round2(state.cash + state.position * price);
  const pnl = round2(portfolio - state.settings.startingCash);
  const returnPct = state.settings.startingCash ? pnl / state.settings.startingCash * 100 : 0;
  $("currentPrice").textContent = money(price);
  $("portfolioValue").textContent = money(portfolio);
  $("profitLoss").textContent = `${pnl >= 0 ? "+" : "−"}${money(Math.abs(pnl))}`;
  $("profitLoss").className = pnl >= 0 ? "positive" : "negative";
  $("returnPercent").textContent = `${returnPct >= 0 ? "+" : "−"}${Math.abs(returnPct).toFixed(2)}%`;
  $("roundTrips").textContent = String(state.events.filter((event) => event.side.startsWith("SALG")).length);
  $("feeTotal").textContent = `Gebyrer: ${money(state.fees)}`;
  $("dayLabel").textContent = `Dag ${state.day || state.prices.length}`;
  $("orderCount").textContent = `${state.totalOrders} ordre`;

  const log = $("tradeLog");
  log.replaceChildren();
  if (state.events.length === 0) {
    const row = log.insertRow();
    row.className = "empty-row";
    const cell = row.insertCell();
    cell.colSpan = 6;
    cell.textContent = "Venter på første signal. Du kan også endre innstillingene.";
  } else {
    for (const event of [...state.events].reverse()) {
      const row = log.insertRow();
      row.className = event.side.startsWith("KJØP") ? "buy-row" : "sell-row";
      for (const text of [
        event.day,
        event.side,
        money(event.price),
        event.quantity,
        money(event.fee),
        money(event.cash),
      ]) {
        row.insertCell().textContent = String(text);
      }
    }
  }
  drawChart(state);
}

function drawChart(state) {
  const canvas = $("priceChart");
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const ratio = Math.max(1, window.devicePixelRatio || 1);
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  const width = rect.width;
  const height = rect.height;
  const pad = { left: 52, right: 14, top: 16, bottom: 22 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const prices = state.prices;
  if (prices.length < 2 || plotWidth <= 0 || plotHeight <= 0) return;
  const fast = movingAverages(prices, state.settings.fastWindow);
  const slow = movingAverages(prices, state.settings.slowWindow);
  const values = prices.concat(fast.filter(Number.isFinite), slow.filter(Number.isFinite));
  const low = Math.min(...values);
  const high = Math.max(...values);
  const margin = Math.max((high - low) * 0.12, 0.5);
  const min = low - margin;
  const max = high + margin;
  const x = (index) => pad.left + index * plotWidth / (prices.length - 1);
  const y = (value) => pad.top + (max - value) * plotHeight / (max - min);

  ctx.clearRect(0, 0, width, height);
  ctx.font = "10px 'DM Mono', Consolas, monospace";
  ctx.textBaseline = "middle";
  for (let step = 0; step <= 4; step++) {
    const value = min + (max - min) * step / 4;
    const yy = y(value);
    ctx.strokeStyle = "#26344a";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.left, yy);
    ctx.lineTo(width - pad.right, yy);
    ctx.stroke();
    ctx.fillStyle = "#8392a9";
    ctx.textAlign = "right";
    ctx.fillText(`$${value.toFixed(0)}`, pad.left - 8, yy);
  }

  const drawLine = (series, color, lineWidth) => {
    ctx.beginPath();
    let started = false;
    series.forEach((value, index) => {
      if (!Number.isFinite(value)) return;
      if (!started) { ctx.moveTo(x(index), y(value)); started = true; }
      else ctx.lineTo(x(index), y(value));
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();
  };
  drawLine(prices, "#90aaff", 2);
  drawLine(fast, "#55d6b0", 1.7);
  drawLine(slow, "#f2bd69", 1.7);

  for (const event of state.events) {
    const index = Math.max(0, Math.min(event.chartIndex ?? event.day - 1, prices.length - 1));
    const px = x(index);
    const py = y(prices[index]);
    ctx.beginPath();
    if (event.side.startsWith("KJØP")) {
      ctx.moveTo(px, py - 8); ctx.lineTo(px - 5, py + 1); ctx.lineTo(px + 5, py + 1);
      ctx.closePath(); ctx.fillStyle = "#55d6b0";
    } else {
      ctx.moveTo(px, py + 8); ctx.lineTo(px - 5, py - 1); ctx.lineTo(px + 5, py - 1);
      ctx.closePath(); ctx.fillStyle = "#ff7185";
    }
    ctx.fill();
  }
}

function setDefaults() {
  for (const [key, value] of Object.entries(DEFAULTS)) $(key).value = value;
  startLive();
}

$("settingsForm").addEventListener("submit", (event) => {
  event.preventDefault();
  startLive();
});
$("pauseButton").addEventListener("click", pauseLive);
$("historyButton").addEventListener("click", runHistorical);
$("resetButton").addEventListener("click", setDefaults);
window.addEventListener("resize", () => appState && drawChart(appState));
startLive();

