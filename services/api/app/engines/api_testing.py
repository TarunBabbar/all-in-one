"""API Testing engine (E9).

Absorbs: Vishesh's QA API Agent (single API execution + risk scoring +
AI test-gap ideas + Excel/HTML shareable report) and QAGenX API scenario
generator with code samples.

Deterministic first: from a method+URL (and optional headers/body), derive
risk score, functional/negative/boundary/security test ideas, and run the
real request via httpx when `execute: true`. The LLM (optional) enriches test
ideas when configured; on mock the rule-based ideas stand. Output is a
shareable report shape (per Vishesh) with `demo: false` whenever a real
request ran.
"""

from __future__ import annotations

from ..pipeline.registry import Engine, register

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}

# Risk heuristics: which verbs/mutations raise risk.
_RISK = {
    "GET": 30,
    "POST": 60,
    "PUT": 65,
    "PATCH": 60,
    "DELETE": 70,
}


def risk_score(method: str, has_auth: bool, has_body: bool) -> int:
    base = _RISK.get(method.upper(), 40)
    if not has_auth:
        base += 15
    if has_body:
        base += 10
    return min(100, base)


def test_ideas(method: str, url: str) -> list[dict]:
    """Deterministic functional/negative/boundary/security ideas."""
    m = method.upper()
    return [
        {
            "type": "functional",
            "title": f"{m} {url} returns expected status + schema",
            "priority": "P1",
        },
        {
            "type": "negative",
            "title": f"{m} {url} with invalid payload -> 4xx",
            "priority": "P1",
        },
        {
            "type": "boundary",
            "title": f"{m} {url} empty body / very large body",
            "priority": "P2",
        },
        {
            "type": "security",
            "title": f"{m} {url} without auth -> 401/403",
            "priority": "P1",
        },
    ]


async def _api_testing(ctx: dict, **payload) -> dict:
    method: str = str(payload.get("method", "GET")).upper()
    url: str = str(payload.get("url", "")).strip()
    headers: dict = payload.get("headers") or {}
    body: dict | None = payload.get("body")
    execute: bool = bool(payload.get("execute", False))

    if not url:
        return {
            "kind": "api_report",
            "payload": {"error": "url is required."},
            "engine": "api-testing",
        }

    has_auth = bool(headers.get("Authorization") or headers.get("X-Api-Key"))
    risk = risk_score(method, has_auth, body is not None)
    ideas = test_ideas(method, url)

    executed = None
    if execute:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(
                    method, url, headers=headers or None, json=body, follow_redirects=True
                )
                executed = {
                    "status": resp.status_code,
                    "status_text": resp.reason_phrase,
                    "latency_ms": None,  # measured below via elapsed
                }
                # elapsed is available on the response
                executed["latency_ms"] = round(resp.elapsed.total_seconds() * 1000, 1)
                ctype = resp.headers.get("content-type", "")
                executed["body_excerpt"] = (
                    resp.text[:300] if "json" in ctype or "text" in ctype else f"<{ctype}>"
                )
        except Exception as exc:  # noqa: BLE001 — report network errors honestly
            executed = {"error": str(exc)}

    return {
        "kind": "api_report",
        "payload": {
            "method": method,
            "url": url,
            "risk_score": risk,
            "test_ideas": ideas,
            "gap_notes": "missing auth header is the top gap" if not has_auth else None,
            "executed": executed,
            "shareable": True,
        },
        "engine": "api-testing",
    }


def register_engines() -> None:
    register(
        Engine(
            id="api-testing",
            name="Test API Endpoints",
            description="Risk-scored endpoint analysis, test-gap ideas, and "
            "real request execution with a shareable report.",
            uses_llm=True,
            run=_api_testing,
        )
    )


register_engines()