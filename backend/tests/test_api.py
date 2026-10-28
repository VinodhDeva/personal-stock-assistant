import io

from app.core.config import get_settings


def test_health(client):
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["real_orders"] is False


def test_providers_status_has_no_secrets(client, monkeypatch):
    s = get_settings()
    from pydantic import SecretStr

    monkeypatch.setattr(s, "telegram_bot_token", SecretStr("999:TOPSECRET"))
    body = client.get("/api/providers/status").text
    assert "TOPSECRET" not in body
    j = client.get("/api/providers/status").json()
    assert j["live_data_available"] is False
    assert j["ollama"]["reachable"] is False


def test_watchlist_crud_and_validation(client):
    assert client.get("/api/watchlist").json() == []
    r = client.post("/api/watchlist", json={"symbol": "reliance", "exchange": "NSE"})
    assert r.status_code == 201 and r.json()["symbol"] == "RELIANCE.NS" and r.json()["name"] == "Reliance Industries"
    assert client.post("/api/watchlist", json={"symbol": "RELIANCE.NS"}).status_code == 409
    bad = client.post("/api/watchlist", json={"symbol": "AAPL.US"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_symbol"
    assert client.post("/api/watchlist", json={"symbol": "NOPE.NS"}).status_code == 404
    assert [w["symbol"] for w in client.get("/api/watchlist").json()] == ["RELIANCE.NS"]
    assert client.delete("/api/watchlist/RELIANCE.NS").status_code == 204
    assert client.delete("/api/watchlist/RELIANCE.NS").status_code == 404


def test_quote_history_indicators_expose_freshness(client):
    q = client.get("/api/stocks/RELIANCE.NS/quote").json()
    assert q["freshness"] == "delayed" and q["provider"] == "yahoo" and q["exchange"] == "NSE"
    assert q["data_timestamp"]
    h = client.get("/api/stocks/RELIANCE.NS/history?period=6mo").json()
    assert h["candles"] and h["freshness"] and h["data_timestamp"]
    i = client.get("/api/stocks/RELIANCE.NS/indicators").json()
    assert i["latest"]["rsi_14"] is not None and i["series"][0]["rsi_14"] is None
    assert client.get("/api/stocks/RELIANCE.NS/history?period=99y").status_code == 422


def test_search_local(client):
    r = client.get("/api/stocks/search?q=infosys").json()
    assert r[0]["symbol"] == "INFY.NS" and r[0]["exchange"] == "NSE"


def test_refresh_generates_signals_and_dedupes(client):
    client.post("/api/watchlist", json={"symbol": "RELIANCE.NS"})
    client.post("/api/signals/refresh")
    client.post("/api/signals/refresh")
    sigs = client.get("/api/signals").json()
    assert sigs["total"] == 1 and sigs["items"][0]["signal_type"] == "BUY"
    assert client.get("/api/signals/latest").json()[0]["symbol"] == "RELIANCE.NS"
    notes = client.get("/api/notifications").json()["items"]
    kinds = [(n["kind"], n["status"]) for n in notes]
    assert kinds.count(("signal", "logged")) == 1  # Telegram not configured -> local log, once
    assert client.get("/api/signals?signal_type=BUY&limit=1").json()["limit"] == 1


def test_alerts_trigger_once(client):
    client.post("/api/watchlist", json={"symbol": "RELIANCE.NS"})
    a = client.post("/api/alerts", json={"symbol": "RELIANCE.NS", "condition": "above", "price": 1}).json()
    assert (
        client.post("/api/alerts", json={"symbol": "RELIANCE.NS", "condition": "sideways", "price": 1}).status_code
        == 422
    )
    client.post("/api/signals/refresh")
    alerts = client.get("/api/alerts").json()
    assert alerts[0]["id"] == a["id"] and alerts[0]["active"] is False and alerts[0]["triggered_price"]


def test_paper_trading_flow(client):
    r = client.post("/api/portfolio/paper-trades", json={"symbol": "RELIANCE.NS", "side": "BUY", "quantity": 10})
    assert r.status_code == 201 and r.json()["price_source"].startswith("yahoo/delayed")
    p = client.get("/api/portfolio").json()
    assert p["simulated"] is True and p["positions"][0]["quantity"] == 10
    bad = client.post("/api/portfolio/paper-trades", json={"symbol": "RELIANCE.NS", "side": "SELL", "quantity": 99})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "insufficient_position"
    assert client.get("/api/portfolio/trades").json()["total"] == 1
    size = client.post("/api/portfolio/position-size", json={"entry": 100, "stop_loss": 95}).json()
    assert size["quantity"] > 0


def test_paper_stop_loss_auto_exit(client):
    client.post(
        "/api/portfolio/paper-trades",
        json={
            "symbol": "RELIANCE.NS",
            "side": "BUY",
            "quantity": 5,
            "price": 500,
            "stop_loss": 400,
            "enforce_risk_limits": False,
        },
    )
    client.post("/api/signals/refresh")  # latest fake price ~180 < stop 400
    trades = client.get("/api/portfolio/trades").json()["items"]
    assert trades[0]["side"] == "SELL" and "stop-loss" in trades[0]["reason"]


def test_assistant_works_without_ollama_and_refuses_trades(client):
    client.post("/api/watchlist", json={"symbol": "RELIANCE.NS"})
    client.post("/api/signals/refresh")
    r = client.post("/api/assistant/chat", json={"message": "Why did RELIANCE generate a BUY signal?"}).json()
    assert r["llm_used"] is False and "Ollama" in r["llm_error"]
    assert "BUY" in r["answer"] and "crossed above" in r["answer"]
    assert r["context"]["signals"][0]["symbol"] == "RELIANCE.NS"
    t = client.post("/api/assistant/chat", json={"message": "buy 100 shares of RELIANCE now"}).json()
    assert t["refused"] is True
    g = client.post("/api/assistant/chat", json={"message": "Explain RSI and ATR"}).json()
    assert "RSI(14)" in g["answer"] and "ATR(14)" in g["answer"]


def test_backtest_endpoint(client):
    r = client.get("/api/backtest/ema_crossover?symbol=TCS.NS").json()
    assert r["num_trades"] >= 1 and r["assumptions"]["fill"] == "next bar open"
    assert client.get("/api/backtest/unknown?symbol=TCS.NS").status_code == 404


def test_settings_roundtrip(client):
    s = client.get("/api/settings").json()
    assert s["strategy"]["rsi_buy_min"] == 45
    new = {**s["strategy"], "rsi_buy_min": 40}
    assert client.put("/api/settings/strategy", json=new).json()["rsi_buy_min"] == 40
    assert client.put("/api/settings/strategy", json={**new, "rsi_buy_min": 80}).status_code == 422
    assert client.put("/api/settings/scheduler", json={"refresh_interval_seconds": 10}).status_code == 422


def test_csv_upload_validation(client):
    good = b"date,open,high,low,close,volume\n2026-01-01,10,11,9,10.5,100\n"
    r = client.post("/api/stocks/TEST.NS/csv", files={"file": ("x.csv", io.BytesIO(good), "text/csv")})
    assert r.status_code == 201 and r.json()["freshness"] == "historical"
    bad = client.post("/api/stocks/TEST.NS/csv", files={"file": ("x.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_csv"


def test_cors_restricted(client):
    ok = client.options(
        "/api/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    evil = client.options(
        "/api/health", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in evil.headers
