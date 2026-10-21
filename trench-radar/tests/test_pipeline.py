import asyncio
import json

import httpx
import pytest

from radar.alerts import detect_changes, dispatch
from radar.analyst import brief, evidence_pack, rules_brief
from radar.analytics.backtest import run_backtest
from radar.analytics.scoring import run_analysis
from radar.db import connect, insert, rows
from radar.sources.base import Http, SourceUnavailable, record_run

from .conftest import H, T0, build_history, make_settings


def test_surging_meta_is_detected_and_explained(history_db):
    res = run_analysis(history_db, T0, persist=False)
    frog = next(m for m in res["metas"] if m["meta_key"] == "frog")
    assert frog["evidence"]["launch"]["launch_accel_z"] > 2
    assert frog["evidence"]["demand"]["unique_buyers_h1_sum"] > 100
    assert frog["score"] > 50 and frog["reasons"] and frog["risks"]
    assert set(frog["components"]) == {"attention", "demand", "market", "freshness"}
    # every number shown has a source: components are within [0, 1]
    assert all(v is None or 0 <= v <= 1 for v in frog["components"].values())
    filler = [m for m in res["metas"] if m["meta_key"] in ("moon", "doge", "pepe")]
    assert all((m["score"] or 0) < frog["score"] for m in filler)


def test_no_lookahead_future_rows_do_not_change_past_analysis(history_db):
    t = T0 - 2 * H
    before = run_analysis(history_db, t, persist=False)
    assert before["lineage"]["max_ts"] <= t
    # add rows that happened before t but were only OBSERVED after t, plus future rows
    insert(history_db, "tokens", {"mint": "LATEpump", "name": "Frog Late", "symbol": "FROG", "pool": "PL",
                                  "launchpad": "pump-fun", "created_at": t - 600, "first_seen_at": t + 60,
                                  "source": "chain"})
    insert(history_db, "token_obs", {"mint": "LATEpump", "observed_at": t + 30, "source": "chain",
                                     "buyers_h1": 999, "vol_h1": 1e6})
    insert(history_db, "social_posts", {"id": "x:late", "source": "x", "author_id": "z", "text": "frog frog",
                                        "created_at": t - 100, "collected_at": t + 5, "fingerprint": "zz"})
    insert(history_db, "graduations", {"mint": "M00001pump", "detected_at": t + 10, "graduated_at": t - 50,
                                       "source": "test"})
    history_db.commit()
    after = run_analysis(history_db, t, persist=False)
    strip = lambda r: [(m["meta_key"], m["score"], m["confidence"]) for m in r["metas"]]  # noqa: E731
    assert strip(before) == strip(after)


def test_confidence_is_low_without_history(tmp_path):
    con = connect(tmp_path / "s.db")
    build_history(con, hours=2)          # only 2h of collection
    res = run_analysis(con, T0, persist=False)
    assert res["context"]["history"]["launch_coverage_baseline"] < 0.5
    assert all(m["evidence"]["launch"]["launch_accel_z"] is None for m in res["metas"])
    assert all(m["verdict"] == "insufficient data" for m in res["metas"])


def test_backtest_runs_without_leaks_and_refuses_to_validate_small_samples(history_db, monkeypatch):
    # outcomes for every token (fabricated test labels): frog tokens graduate more often
    for r in rows(history_db, "SELECT mint, name FROM tokens"):
        hot = r["name"].startswith("Frog")
        insert(history_db, "token_outcomes", {
            "mint": r["mint"], "horizon_h": 24, "evaluated_at": T0, "graduated": int(hot and hash(r["mint"]) % 3 == 0),
            "bucket": "dead", "ret_end": 0.5 if hot else -0.5, "source": "test"})
    history_db.commit()
    import radar.analytics.backtest as bt
    monkeypatch.setattr(bt, "now", lambda: T0 + 40 * H)   # pretend the follow windows have elapsed
    res = run_backtest(history_db, T0 - 8 * H, T0, step_s=2 * H, follow_h=2, horizon_h=24, persist=False)
    assert res["leaked_steps_skipped"] == 0
    assert res["validated"] is False      # far too few signals to claim anything
    assert "not validated" in res["verdict"]


def test_source_failure_is_recorded_and_secrets_redacted(tmp_path):
    s = make_settings(tmp_path, x_bearer_token="SECRETTOKEN123")
    con = connect(s.db_path)

    def handler(request):
        return httpx.Response(403, text="<title>Just a moment...</title>")
    http = Http(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    async def go():
        async with record_run(con, s, "pumpfun", "latest_coins"):
            await http.get_json("https://frontend-api-v3.pump.fun/coins?token=SECRETTOKEN123")
    asyncio.run(go())
    r = rows(con, "SELECT status, error FROM source_runs")[0]
    assert r["status"] == "unavailable" and "Cloudflare" in r["error"]
    assert "SECRETTOKEN123" not in s.redact("bearer SECRETTOKEN123 api_key=abc")
    assert "abc" not in s.redact("x?api_key=abc")
    assert "SECRETTOKEN123" not in json.dumps(s.public_view())


def test_unconfigured_social_is_skipped_not_failed(tmp_path):
    from radar import collectors as c
    s = make_settings(tmp_path)
    con = connect(s.db_path)

    def handler(request):
        return httpx.Response(403, text="blocked")
    http = Http(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    asyncio.run(c.collect_social(c.Ctx(con, s, http)))
    st = {(r["source"], r["status"]) for r in rows(con, "SELECT source, status FROM source_runs")}
    assert ("x_api", "skipped") in st and ("reddit", "unavailable") in st


def test_alerts_detect_verdict_change_and_respect_cooldown(history_db, tmp_path, monkeypatch):
    s = make_settings(tmp_path)
    res = run_analysis(history_db, T0, persist=True)
    frog = next(m for m in res["metas"] if m["meta_key"] == "frog")
    insert(history_db, "scores", {"meta_key": "frog", "computed_at": T0 - 600, "score": 10, "confidence": 0.9,
                                  "verdict": "unfavorable" if frog["verdict"] == "favorable" else "favorable",
                                  "model_version": "x", "detail": "{}"})
    history_db.commit()
    ev = detect_changes(history_db, s, res)
    assert any(e["meta_key"] == "frog" for e in ev)
    sent_payloads = []

    def handler(request):
        sent_payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})
    s2 = make_settings(tmp_path, telegram_bot_token="123:ABC", telegram_chat_id="42")
    http = Http(s2, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    import radar.alerts as al
    monkeypatch.setattr(al, "now", lambda: T0)
    assert asyncio.run(dispatch(history_db, s2, http, ev)) == len(ev)
    assert sent_payloads and sent_payloads[0]["chat_id"] == "42"
    assert not [e for e in detect_changes(history_db, s, res) if e["meta_key"] == "frog"]  # cooldown


def test_analyst_falls_back_to_rules_when_claude_fails(history_db, tmp_path, monkeypatch):
    res = run_analysis(history_db, T0, persist=False)
    pack = evidence_pack(res, None)
    assert "frog" in rules_brief(pack)
    import radar.analyst as an

    async def boom(*a, **k):
        raise RuntimeError("api down")
    monkeypatch.setattr(an, "claude_brief", boom)
    text, who = asyncio.run(brief(make_settings(tmp_path, anthropic_api_key="sk-test"), pack))
    assert who == "rules" and "Claude analyst unavailable" in text
    json.dumps(pack)  # evidence pack must be serialisable for storage


def test_api_requires_token_when_configured(tmp_path):
    from fastapi.testclient import TestClient

    from radar.api import create_app
    s = make_settings(tmp_path, dashboard_token="letmein")
    build_history(connect(s.db_path), hours=6)
    with TestClient(create_app(s)) as client:
        assert client.get("/api/overview").status_code == 401
        r = client.get("/api/overview", headers={"x-radar-token": "letmein"})
        assert r.status_code == 200
        body = r.json()
        assert "metas" in body and "freshness" in body and body["config"]["x_api"] is False
        assert "letmein" not in r.text


def test_http_retries_then_raises_unavailable(tmp_path, monkeypatch):
    s = make_settings(tmp_path)
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503)
    http = Http(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    import radar.sources.base as b
    async def nosleep(_):
        return None
    monkeypatch.setattr(b.asyncio, "sleep", nosleep)
    with pytest.raises(SourceUnavailable):
        asyncio.run(http.get_json("https://example.org/x", retries=2))
    assert len(calls) == 3


def test_claude_analyst_request_shape_against_stub_server(history_db, tmp_path, monkeypatch):
    """Runs the real Anthropic SDK against a local stub to check what we send; no network, no key."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = {}

    class Stub(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["beta"] = self.headers.get("anthropic-beta")
            seen["body"] = json.loads(self.rfile.read(int(self.headers["content-length"])))
            out = json.dumps({"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                              "content": [{"type": "text", "text": "**Bottom line** — stub."}],
                              "stop_reason": "end_turn", "stop_sequence": None,
                              "usage": {"input_tokens": 10, "output_tokens": 5}}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{srv.server_port}")
    pack = evidence_pack(run_analysis(history_db, T0, persist=False), None)
    try:
        text, who = asyncio.run(brief(make_settings(tmp_path, anthropic_api_key="sk-test"), pack))
    finally:
        srv.shutdown()
    assert who == "claude:claude-opus-5-5" and "stub" in text
    body = seen["body"]
    assert seen["path"].startswith("/v1/messages") and "server-side-fallback-2026-07-01" in seen["beta"]
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default"
    assert "Evidence pack" in body["messages"][0]["content"] and "frog" in body["messages"][0]["content"]
    assert "Every number you state must appear in it" in body["system"]


def test_x_read_budget_is_enforced(tmp_path):
    from radar import collectors as c
    s = make_settings(tmp_path, x_bearer_token="tok", x_queries=["a", "b"], x_daily_read_budget=15, x_max_results=10)
    con = connect(s.db_path)
    calls = []

    def handler(request):
        calls.append(request.url.params["max_results"])
        n = int(request.url.params["max_results"])
        data = [{"id": str(1000 + len(calls) * 100 + i), "text": "frog", "author_id": "u",
                 "created_at": "2026-10-16T00:00:00Z", "public_metrics": {}} for i in range(n)]
        return httpx.Response(200, json={"data": data, "includes": {"users": [{"id": "u", "username": "u"}]}})
    http = Http(s, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    asyncio.run(c.collect_social(c.Ctx(con, s, http)))
    assert calls == ["10"]          # 5 left < X's minimum page of 10: stop rather than overspend
    asyncio.run(c.collect_social(c.Ctx(con, s, http)))
    assert len(calls) == 1          # budget spent: no more paid reads today
    assert ("x_api", "skipped") in {(r["source"], r["status"]) for r in rows(con, "SELECT source, status FROM source_runs")}


def test_dashboard_endpoints_serve_real_rows(tmp_path):
    from fastapi.testclient import TestClient

    from radar.api import create_app
    s = make_settings(tmp_path)
    con = connect(s.db_path)
    build_history(con, now_ts=__import__("time").time().__int__(), hours=6)
    with TestClient(create_app(s)) as client:
        ch = client.get("/api/charts?hours=6").json()
        assert ch["step_s"] == 300 and ch["launches"] and ch["observed_buckets"]
        toks = client.get("/api/tokens").json()["tokens"]
        assert toks and all(t["vol_h1"] is not None for t in toks)
        d = client.get(f"/api/tokens/{toks[0]['mint']}").json()
        assert d["token"]["mint"] == toks[0]["mint"] and d["observations"]
        assert client.get("/api/tokens/nope").status_code == 404
        assert "deployer_launches_24h" in toks[0]
        assert client.get("/api/reports").json() == [] and client.get("/api/reports/1").status_code == 404
        assert client.get("/manifest.webmanifest").status_code == 200


def test_seven_hours_of_history_is_enough_for_calls(tmp_path):
    con = connect(tmp_path / "s.db")
    build_history(con, hours=8)
    res = run_analysis(con, T0, persist=False)
    assert res["context"]["history"]["launch_coverage_baseline"] >= 0.5
    frog = next(m for m in res["metas"] if "frog" in m["terms"])
    assert frog["evidence"]["launch"]["launch_accel_z"] is not None
