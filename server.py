import os
import time
import json
import hashlib
import sqlite3
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional, List
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv


# =========================
# Paths / env
# =========================
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
DASH_DIR = BASE_DIR / "dashboard"

load_dotenv(dotenv_path=ENV_PATH)

CAPITAL_BASE_URL = os.getenv("CAPITAL_BASE_URL", "https://demo-api-capital.backend-capital.com").rstrip("/")
CAPITAL_API_KEY = os.getenv("CAPITAL_API_KEY", "")
CAPITAL_ACCOUNT_IDENTIFIER = os.getenv("CAPITAL_ACCOUNT_IDENTIFIER", "")
CAPITAL_API_PASSWORD = os.getenv("CAPITAL_API_PASSWORD", "")
CAPITAL_ACCOUNT_ID = os.getenv("CAPITAL_ACCOUNT_ID", "")

WEBHOOK_PASSPHRASE = os.getenv("WEBHOOK_PASSPHRASE", "")

DB_PATH = os.getenv("DB_PATH", "trading.db")
DASH_TOKEN = os.getenv("DASH_TOKEN", "")

SESSION_TTL_SECONDS = 9 * 60
SEEN_TTL_SECONDS = 60

_session: Dict[str, Any] = {"cst": None, "xst": None, "expires_at": 0.0}
_seen: Dict[str, float] = {}
POSITIONS_BY_EPIC: Dict[str, str] = {}

# NEW: per-epic locks so OPEN/CLOSE cannot race on same instrument
_EPIC_LOCKS: Dict[str, asyncio.Lock] = {}


def epic_lock(epic: str) -> asyncio.Lock:
    lock = _EPIC_LOCKS.get(epic)
    if lock is None:
        lock = asyncio.Lock()
        _EPIC_LOCKS[epic] = lock
    return lock


# =========================
# Helpers
# =========================
def now() -> float:
    return time.time()


def require_env() -> None:
    missing = [k for k, v in {
        "CAPITAL_API_KEY": CAPITAL_API_KEY,
        "CAPITAL_ACCOUNT_IDENTIFIER": CAPITAL_ACCOUNT_IDENTIFIER,
        "CAPITAL_API_PASSWORD": CAPITAL_API_PASSWORD,
        "WEBHOOK_PASSPHRASE": WEBHOOK_PASSPHRASE,
        "DASH_TOKEN": DASH_TOKEN,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"Mangler miljøvariabler: {', '.join(missing)}")


def require_dash(request: Request) -> None:
    token = request.query_params.get("token") or request.headers.get("x-dash-token")
    if not token or token != DASH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized (missing/invalid dashboard token).")


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def db_init() -> None:
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            source TEXT NOT NULL,
            event_type TEXT NOT NULL,
            epic TEXT,
            action TEXT,
            payload_json TEXT,
            response_json TEXT,
            ok INTEGER NOT NULL
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_open REAL,
            ts_close REAL,
            epic TEXT NOT NULL,
            direction TEXT,
            size REAL,
            level_open REAL,
            level_close REAL,
            stop_level REAL,
            deal_reference_open TEXT,
            deal_id TEXT,
            status TEXT NOT NULL DEFAULT 'OPEN'
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_open ON trades(ts_open)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_epic ON trades(epic)")
        conn.commit()


def log_event(source: str, event_type: str, epic: Optional[str], action: Optional[str],
              payload: Optional[Dict[str, Any]], response: Optional[Dict[str, Any]], ok: bool) -> None:
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO events(ts,source,event_type,epic,action,payload_json,response_json,ok) VALUES(?,?,?,?,?,?,?,?)",
                (
                    now(),
                    source,
                    event_type,
                    epic,
                    action,
                    json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                    json.dumps(response, ensure_ascii=False) if response is not None else None,
                    1 if ok else 0,
                ),
            )
            conn.commit()
    except Exception:
        pass


def insert_trade_open(epic: str, direction: str, size: float, level_open: Optional[float],
                      stop_level: Optional[float], deal_reference: Optional[str], deal_id: Optional[str]) -> None:
    try:
        with db() as conn:
            conn.execute(
                """
                INSERT INTO trades(ts_open, epic, direction, size, level_open, stop_level,
                                   deal_reference_open, deal_id, status)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (now(), epic, direction, size, level_open, stop_level, deal_reference, deal_id, "OPEN"),
            )
            conn.commit()
    except Exception:
        pass


def close_trade(epic: str, deal_id: Optional[str], level_close: Optional[float]) -> None:
    try:
        with db() as conn:
            if deal_id:
                conn.execute(
                    """
                    UPDATE trades
                    SET ts_close=?, level_close=?, status='CLOSED'
                    WHERE deal_id=? AND status='OPEN'
                    """,
                    (now(), level_close, deal_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE trades
                    SET ts_close=?, level_close=?, status='CLOSED'
                    WHERE id = (
                        SELECT id FROM trades WHERE epic=? AND status='OPEN' ORDER BY ts_open DESC LIMIT 1
                    )
                    """,
                    (now(), level_close, epic),
                )
            conn.commit()
    except Exception:
        pass


def calc_points_pl(direction: Optional[str], size: Optional[float],
                   level_open: Optional[float], level_close: Optional[float]) -> Optional[float]:
    if not direction or size is None or level_open is None or level_close is None:
        return None
    d = direction.upper()
    sign = 1.0 if d == "BUY" else -1.0 if d == "SELL" else 0.0
    if sign == 0.0:
        return None
    return (level_close - level_open) * sign * float(size)


def as_float(x) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().replace(",", ".")
        try:
            return float(s)
        except Exception:
            return None
    return None


def dedupe_key(payload: Dict[str, Any]) -> str:
    for k in ("id", "alert_id", "signal_id", "uuid"):
        if payload.get(k):
            return f"{k}:{payload.get(k)}"
    raw = "|".join([
        str(payload.get("action", "")).upper(),
        str(payload.get("epic", "")).upper(),
        str(payload.get("side", "")).upper(),
        str(payload.get("size", "")),
        str(payload.get("time", "")),
    ])
    return "hash:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def dedupe_check_and_mark(key: str) -> bool:
    t = now()
    for k in [k for k, ts in _seen.items() if (t - ts) > SEEN_TTL_SECONDS]:
        _seen.pop(k, None)
    if key in _seen:
        return False
    _seen[key] = t
    return True


# =========================
# Capital API
# =========================
async def capital_login(client: httpx.AsyncClient) -> None:
    require_env()

    r = await client.post(
        f"{CAPITAL_BASE_URL}/api/v1/session",
        headers={"X-CAP-API-KEY": CAPITAL_API_KEY},
        json={"identifier": CAPITAL_ACCOUNT_IDENTIFIER, "password": CAPITAL_API_PASSWORD, "encryptedPassword": False},
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Capital login feilet: {r.status_code} {r.text}")

    cst = r.headers.get("CST")
    xst = r.headers.get("X-SECURITY-TOKEN")
    if not cst or not xst:
        raise HTTPException(status_code=502, detail="Capital login mangler CST/X-SECURITY-TOKEN i respons-header.")

    _session["cst"] = cst
    _session["xst"] = xst
    _session["expires_at"] = now() + SESSION_TTL_SECONDS

    if CAPITAL_ACCOUNT_ID:
        put = await client.put(
            f"{CAPITAL_BASE_URL}/api/v1/session",
            headers={"X-CAP-API-KEY": CAPITAL_API_KEY, "CST": cst, "X-SECURITY-TOKEN": xst},
            json={"accountId": CAPITAL_ACCOUNT_ID},
            timeout=20.0,
        )
        if put.status_code >= 400 and "error.not-different.accountId" not in put.text:
            raise HTTPException(status_code=502, detail=f"PUT /session feilet: {put.status_code} {put.text}")


async def capital_headers(client: httpx.AsyncClient) -> Dict[str, str]:
    if _session["cst"] and _session["xst"] and _session["expires_at"] > now():
        return {"X-CAP-API-KEY": CAPITAL_API_KEY, "CST": _session["cst"], "X-SECURITY-TOKEN": _session["xst"]}
    await capital_login(client)
    return {"X-CAP-API-KEY": CAPITAL_API_KEY, "CST": _session["cst"], "X-SECURITY-TOKEN": _session["xst"]}


async def capital_request(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> httpx.Response:
    headers = await capital_headers(client)
    r = await client.request(method, f"{CAPITAL_BASE_URL}{path}", headers=headers, timeout=20.0, **kwargs)
    if r.status_code in (401, 403):
        await capital_login(client)
        headers = await capital_headers(client)
        r = await client.request(method, f"{CAPITAL_BASE_URL}{path}", headers=headers, timeout=20.0, **kwargs)
    return r


async def list_positions(client: httpx.AsyncClient) -> Dict[str, Any]:
    r = await capital_request(client, "GET", "/api/v1/positions")
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"GET /positions feilet: {r.status_code} {r.text}")
    return r.json()


async def list_accounts(client: httpx.AsyncClient) -> Dict[str, Any]:
    r = await capital_request(client, "GET", "/api/v1/accounts")
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"GET /accounts feilet: {r.status_code} {r.text}")
    return r.json()


def pick_account(accounts_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    accounts = accounts_payload.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        return None
    if CAPITAL_ACCOUNT_ID:
        for a in accounts:
            if str(a.get("accountId") or "") == str(CAPITAL_ACCOUNT_ID):
                return a
    return accounts[0]


def extract_account_metrics(account: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mappet 1:1 mot din respons:
      balance.deposit   = Funds
      balance.profitLoss= P&L
      balance.balance   = Equity
    """
    bal = account.get("balance") if isinstance(account.get("balance"), dict) else {}
    funds = as_float(bal.get("deposit"))
    pnl = as_float(bal.get("profitLoss"))
    equity = as_float(bal.get("balance"))
    margin = as_float(bal.get("margin"))

    if equity is None and funds is not None and pnl is not None:
        equity = funds + pnl

    return {"funds": funds, "pnl": pnl, "equity": equity, "margin": margin}


async def confirm(client: httpx.AsyncClient, deal_reference: str) -> Dict[str, Any]:
    r = await capital_request(client, "GET", f"/api/v1/confirms/{deal_reference}")
    if r.status_code >= 400:
        return {"dealReference": deal_reference, "confirm_error": r.text}
    return r.json()


def list_dealids_for_epic(positions_payload: Dict[str, Any], epic: str) -> List[str]:
    out: List[str] = []
    positions = positions_payload.get("positions") if isinstance(positions_payload, dict) else None
    if not isinstance(positions, list):
        return out
    for p in positions:
        if not isinstance(p, dict):
            continue
        position = p.get("position") or {}
        market = p.get("market") or {}
        pos_epic = (market.get("epic") or position.get("epic"))
        if str(pos_epic) == str(epic):
            deal_id = position.get("dealId")
            if deal_id:
                out.append(str(deal_id))
    return out


def positions_for_epic(positions_payload: Dict[str, Any], epic: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    positions = positions_payload.get("positions") if isinstance(positions_payload, dict) else None
    if not isinstance(positions, list):
        return out
    for p in positions:
        if not isinstance(p, dict):
            continue
        position = p.get("position") or {}
        market = p.get("market") or {}
        pos_epic = (market.get("epic") or position.get("epic"))
        if str(pos_epic) == str(epic):
            out.append(p)
    return out


def any_opposite_direction(epic_positions: List[Dict[str, Any]], desired_side: str) -> bool:
    desired = desired_side.upper()
    for p in epic_positions:
        position = (p or {}).get("position") or {}
        d = str(position.get("direction") or "").upper()
        if d and d != desired:
            return True
    return False


async def close_all_for_epic(client: httpx.AsyncClient, epic: str) -> List[Dict[str, Any]]:
    pos = await list_positions(client)
    deal_ids = list_dealids_for_epic(pos, epic)
    results: List[Dict[str, Any]] = []
    for did in deal_ids:
        results.append(await close_by_dealid(client, epic, did))
    return results


def build_open_payload(epic: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    side = str(payload.get("side", "")).upper()
    if side not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="side må være BUY eller SELL.")
    size = float(payload.get("size", 1))

    body: Dict[str, Any] = {"epic": epic, "direction": side, "size": size}

    for k in ("stopLevel", "stopDistance", "profitLevel", "profitDistance", "guaranteedStop", "trailingStop"):
        if k in payload and payload[k] not in (None, ""):
            body[k] = payload[k]

    for k in ("stopLevel", "stopDistance", "profitLevel", "profitDistance"):
        if k in body:
            body[k] = float(body[k])

    return body


async def open_position(client: httpx.AsyncClient, epic: str, body: Dict[str, Any]) -> Dict[str, Any]:
    r = await capital_request(client, "POST", "/api/v1/positions", json=body)
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"POST /positions feilet: {r.status_code} {r.text}")

    data = r.json()
    deal_ref = data.get("dealReference")
    conf = await confirm(client, deal_ref) if deal_ref else {"note": "No dealReference"}

    deal_id = conf.get("dealId")
    if deal_id and (conf.get("dealStatus") or "").upper() == "ACCEPTED":
        POSITIONS_BY_EPIC[epic] = str(deal_id)

    insert_trade_open(
        epic=epic,
        direction=body.get("direction"),
        size=float(body.get("size", 0)),
        level_open=as_float(conf.get("level")),
        stop_level=as_float(body.get("stopLevel")),
        deal_reference=deal_ref,
        deal_id=str(deal_id) if deal_id else None,
    )

    return {"dealReference": deal_ref, "open_response": data, "confirm": conf}


async def close_by_dealid(client: httpx.AsyncClient, epic: str, deal_id: str) -> Dict[str, Any]:
    r = await capital_request(client, "DELETE", f"/api/v1/positions/{deal_id}")
    if r.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"DELETE /positions/{deal_id} feilet: {r.status_code} {r.text}")

    data = r.json()
    deal_ref = data.get("dealReference")
    conf = await confirm(client, deal_ref) if deal_ref else {"note": "No dealReference"}

    POSITIONS_BY_EPIC.pop(epic, None)
    close_trade(epic=epic, deal_id=deal_id, level_close=as_float(conf.get("level")))

    return {"dealReference": deal_ref, "close_response": data, "confirm": conf}


# =========================
# Lifespan + app
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    db_init()
    log_event("system", "startup", None, None, {"base_url": CAPITAL_BASE_URL}, None, True)
    yield


app = FastAPI(title="TradingView → Capital.com Bridge", lifespan=lifespan)

if DASH_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(DASH_DIR), html=False), name="static")


# =========================
# Dashboard + APIs
# =========================
@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    require_dash(request)
    index_path = DASH_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="dashboard/index.html mangler.")
    return FileResponse(str(index_path))


@app.get("/api/summary")
async def api_summary(request: Request):
    require_dash(request)

    # Realized points from DB
    with db() as conn:
        rows = conn.execute("""
            SELECT ts_open, ts_close, epic, direction, size, level_open, level_close, status
            FROM trades
            ORDER BY ts_open ASC
        """).fetchall()

    closed_points: List[float] = []
    equity_curve_points: List[Dict[str, Any]] = []
    eq_pts = 0.0

    for r in rows:
        if r["status"] == "CLOSED":
            pnl = calc_points_pl(r["direction"], r["size"], r["level_open"], r["level_close"])
            if pnl is not None:
                closed_points.append(pnl)
                eq_pts += pnl
                equity_curve_points.append({"ts": r["ts_close"] or r["ts_open"], "equity": eq_pts})

    realized_points = float(sum(closed_points)) if closed_points else 0.0
    wins = sum(1 for x in closed_points if x > 0)
    losses = sum(1 for x in closed_points if x < 0)
    winrate = (wins / (wins + losses) * 100.0) if (wins + losses) > 0 else 0.0

    # Account-level metrics + open positions table
    account_metrics = {"funds": None, "pnl": None, "equity": None, "margin": None}
    open_positions: List[Dict[str, Any]] = []
    pnl_fallback_sum = 0.0

    async with httpx.AsyncClient() as client:
        try:
            accs = await list_accounts(client)
            acc = pick_account(accs)
            if acc:
                account_metrics = extract_account_metrics(acc)
        except Exception:
            pass

        try:
            pos = await list_positions(client)
            for p in (pos.get("positions") or []):
                position = p.get("position") or {}
                market = p.get("market") or {}

                upl_raw = (
                    position.get("unrealisedProfitLoss")
                    if "unrealisedProfitLoss" in position
                    else position.get("unrealizedProfitLoss")
                )
                if upl_raw is None:
                    upl_raw = position.get("profitLoss")
                if upl_raw is None:
                    upl_raw = position.get("pnl")

                upl = as_float(upl_raw)
                if upl is not None:
                    pnl_fallback_sum += upl

                open_positions.append({
                    "epic": market.get("epic") or position.get("epic"),
                    "direction": position.get("direction"),
                    "size": position.get("size"),
                    "level": position.get("level"),
                    "stopLevel": position.get("stopLevel"),
                    "upl": upl,
                    "upl_raw": upl_raw,
                })
        except Exception:
            pass

    pnl_currency = account_metrics["pnl"]
    if pnl_currency is None:
        pnl_currency = pnl_fallback_sum

    return {
        "ok": True,
        "base_url": CAPITAL_BASE_URL,

        "funds_currency": account_metrics["funds"],
        "pnl_currency": pnl_currency,
        "equity_currency": account_metrics["equity"],
        "margin_currency": account_metrics["margin"],

        "realized_points": realized_points,
        "winrate": winrate,
        "wins": wins,
        "losses": losses,
        "equity_curve_points": equity_curve_points[-500:],

        "open_positions": open_positions[:200],
    }


@app.get("/api/trades")
async def api_trades(request: Request, limit: int = 100):
    require_dash(request)
    limit = max(1, min(limit, 1000))
    with db() as conn:
        rows = conn.execute("""
            SELECT ts_open, ts_close, epic, direction, size, level_open, level_close, stop_level, deal_id, status
            FROM trades
            ORDER BY ts_open DESC
            LIMIT ?
        """, (limit,)).fetchall()

    items = []
    for r in rows:
        pnl = calc_points_pl(r["direction"], r["size"], r["level_open"], r["level_close"]) if r["status"] == "CLOSED" else None
        items.append({**dict(r), "pnl_points": pnl})

    return {"ok": True, "items": items}


@app.get("/api/events")
async def api_events(request: Request, limit: int = 100):
    require_dash(request)
    limit = max(1, min(limit, 1000))
    with db() as conn:
        rows = conn.execute("""
            SELECT ts, source, event_type, epic, action, ok
            FROM events
            ORDER BY ts DESC
            LIMIT ?
        """, (limit,)).fetchall()
    return {"ok": True, "items": [dict(r) for r in rows]}


@app.get("/health")
async def health():
    return {"ok": True, "base_url": CAPITAL_BASE_URL}


# =========================
# Webhook
# =========================
@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    if not body:
        log_event("webhook", "empty_body", None, None, None, {"detail": "Empty body"}, False)
        raise HTTPException(status_code=400, detail="Tom request body (TradingView test alert).")

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        log_event("webhook", "bad_json", None, None, {"raw": body.decode("utf-8", errors="ignore")}, None, False)
        raise HTTPException(status_code=400, detail="Ugyldig JSON i request body.")

    action = str(payload.get("action", "OPEN")).upper()
    epic = str(payload.get("epic") or "").strip()

    if payload.get("passphrase") != WEBHOOK_PASSPHRASE:
        log_event("webhook", "bad_passphrase", epic or None, action, payload, {"detail": "bad passphrase"}, False)
        raise HTTPException(status_code=401, detail="Ugyldig passphrase.")

    key = dedupe_key(payload)
    if not dedupe_check_and_mark(key):
        log_event("webhook", "deduped", epic or None, action, payload, {"deduped": True, "key": key}, True)
        return {"ok": True, "deduped": True, "key": key}

    if not epic:
        resp = {"ok": False, "detail": "Mangler epic i payload (Pine skal sende epic)."}
        log_event("webhook", "bad_payload", None, action, payload, resp, False)
        raise HTTPException(status_code=400, detail=resp["detail"])

    async with httpx.AsyncClient() as client:
        try:
            # NEW: serialize per instrument so flips on same bar are deterministic
            async with epic_lock(epic):
                if action == "OPEN":
                    sent = build_open_payload(epic, payload)

                    # NEW: if opposite positions exist -> close them first (closeAll), then open
                    pos = await list_positions(client)
                    epic_pos = positions_for_epic(pos, epic)

                    closed_first: List[Dict[str, Any]] = []
                    if epic_pos and any_opposite_direction(epic_pos, sent["direction"]):
                        closed_first = await close_all_for_epic(client, epic)

                    result = await open_position(client, epic, sent)

                    resp = {
                        "ok": True,
                        "key": key,
                        "action": action,
                        "epic": epic,
                        "sent": sent,
                        "closed_first_count": len(closed_first),
                        "result": result,
                    }
                    log_event("webhook", "open", epic, action, payload, resp, True)
                    return resp

                if action == "CLOSE":
                    close_all = bool(payload.get("closeAll", False))

                    pos = await list_positions(client)
                    deal_ids = list_dealids_for_epic(pos, epic)

                    if not deal_ids:
                        resp = {"ok": False, "detail": f"Fant ingen åpne posisjoner for {epic} å lukke."}
                        log_event("webhook", "close_not_found", epic, action, payload, resp, False)
                        raise HTTPException(status_code=404, detail=resp["detail"])

                    if close_all:
                        results: List[Dict[str, Any]] = []
                        for did in deal_ids:
                            results.append(await close_by_dealid(client, epic, did))
                        resp = {"ok": True, "key": key, "action": action, "epic": epic, "closed": deal_ids, "results": results}
                        log_event("webhook", "close_all", epic, action, payload, resp, True)
                        return resp
                    else:
                        did = deal_ids[0]
                        result = await close_by_dealid(client, epic, did)
                        resp = {"ok": True, "key": key, "action": action, "epic": epic, "dealId": did, "result": result}
                        log_event("webhook", "close_one", epic, action, payload, resp, True)
                        return resp

                resp = {"ok": False, "detail": "Ugyldig action. Bruk OPEN eller CLOSE."}
                log_event("webhook", "bad_action", epic, action, payload, resp, False)
                raise HTTPException(status_code=400, detail=resp["detail"])

        except HTTPException as e:
            log_event("webhook", "http_exception", epic, action, payload, {"detail": e.detail}, False)
            raise
        except Exception as e:
            log_event("webhook", "exception", epic, action, payload, {"error": str(e)}, False)
            raise HTTPException(status_code=500, detail=f"Serverfeil: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
