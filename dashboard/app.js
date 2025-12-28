const TOKEN = new URLSearchParams(location.search).get("token");
const t0 = Date.now();
let eqChart = null;

async function jget(path) {
  const url =
    path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(TOKEN || "");
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return await r.json();
}

function fmt(n, d = 2) {
  if (n === null || n === undefined) return "—";
  if (typeof n === "number") return n.toFixed(d);
  const asNum = Number(String(n).replace(",", "."));
  return Number.isFinite(asNum) ? asNum.toFixed(d) : String(n);
}

function setStatus(ok, text) {
  document.getElementById("statusText").textContent = text;
  const dot = document.getElementById("dot");
  dot.className = "dot " + (ok ? "ok" : "bad");
}

function renderEq(points) {
  const ctx = document.getElementById("eqChart").getContext("2d");
  const labels = points.map((p) =>
    new Date((p.ts || Date.now() / 1000) * 1000).toLocaleTimeString()
  );
  const vals = points.map((p) => p.equity);

  if (eqChart) {
    eqChart.data.labels = labels;
    eqChart.data.datasets[0].data = vals;
    eqChart.update();
    return;
  }

  eqChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [{ label: "Equity (pts)", data: vals, borderWidth: 2, pointRadius: 0, tension: 0.25 }],
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false }, tooltip: { mode: "index", intersect: false } },
      scales: {
        x: { ticks: { color: "rgba(255,255,255,0.55)" }, grid: { color: "rgba(255,255,255,0.06)" } },
        y: { ticks: { color: "rgba(255,255,255,0.55)" }, grid: { color: "rgba(255,255,255,0.06)" } },
      },
    },
  });
}

async function refreshAll() {
  try {
    const s = await jget("/api/summary");
    setStatus(true, "Live");

    document.getElementById("baseUrl").textContent = "Capital base URL: " + s.base_url;

    // Dette er "Capital-style": P&L og Equity på kontonivå
    document.getElementById("unreal").textContent = fmt(s.pnl_currency, 2);

    const equityEl = document.getElementById("equity");
    if (equityEl) equityEl.textContent = fmt(s.equity_currency, 2);

    document.getElementById("realized").textContent = fmt(s.realized_points, 2);
    document.getElementById("winrate").textContent = fmt(s.winrate, 1) + "%";
    document.getElementById("wl").textContent = `${s.wins}W / ${s.losses}L`;
    document.getElementById("runtime").textContent = Math.floor((Date.now() - t0) / 1000) + "s";

    // Open positions
    const posBody = document.getElementById("posBody");
    posBody.innerHTML = "";
    for (const p of s.open_positions || []) {
      const upl = p.upl !== null && p.upl !== undefined ? p.upl : p.upl_raw;
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${p.epic || "—"}</td>
                      <td>${p.direction || "—"}</td>
                      <td>${fmt(p.size, 2)}</td>
                      <td>${fmt(p.level, 2)}</td>
                      <td>${fmt(p.stopLevel, 2)}</td>
                      <td>${fmt(upl, 2)}</td>`;
      posBody.appendChild(tr);
    }

    // Equity curve (points, from closed trades)
    renderEq(s.equity_curve_points || []);

    // Trades
    const trades = await jget("/api/trades?limit=30");
    const trBody = document.getElementById("trBody");
    trBody.innerHTML = "";
    for (const t of trades.items || []) {
      const ts = t.ts_open ? new Date(t.ts_open * 1000).toLocaleString() : "—";
      const pnl = t.pnl_points;
      const cls = typeof pnl === "number" ? (pnl >= 0 ? "good" : "bad") : "";
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${ts}</td>
                      <td>${t.epic}</td>
                      <td>${t.direction || "—"}</td>
                      <td>${fmt(t.size, 2)}</td>
                      <td class="${cls}">${pnl == null ? "—" : fmt(pnl, 2)}</td>
                      <td>${t.status}</td>`;
      trBody.appendChild(tr);
    }

    // Events
    const events = await jget("/api/events?limit=30");
    const evBody = document.getElementById("evBody");
    evBody.innerHTML = "";
    for (const e of events.items || []) {
      const ts = new Date(e.ts * 1000).toLocaleString();
      const ok = e.ok ? `<span class="good">yes</span>` : `<span class="bad">no</span>`;
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${ts}</td>
                      <td>${e.event_type}</td>
                      <td>${e.epic || "—"}</td>
                      <td>${e.action || "—"}</td>
                      <td>${ok}</td>`;
      evBody.appendChild(tr);
    }
  } catch (err) {
    setStatus(false, "Error");
    console.error(err);
  }
}

document.getElementById("btnRefresh").addEventListener("click", refreshAll);
refreshAll();
setInterval(refreshAll, 5000);
