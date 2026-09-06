"""Origins registry tests: 41 rows, uniqueness, endpoints, tag filtering."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.origins.models import Origin
from app.origins.seed import ORIGINS

client = TestClient(app)


def test_seed_has_exactly_41_origins() -> None:
    assert len(ORIGINS) == 41


def test_ranks_are_unique_and_sequential() -> None:
    ranks = [o.rank for o in ORIGINS]
    assert len(ranks) == len(set(ranks))
    assert ranks == list(range(1, 42))


def test_every_origin_has_repo_and_valid_tags() -> None:
    for o in ORIGINS:
        assert o.name
        assert o.project
        assert o.repo.startswith("https://")
        assert o.tags, f"{o.project} has no capability tags"


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_all() -> None:
    r = client.get("/origins")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 41


def test_count_endpoint() -> None:
    r = client.get("/origins/count")
    assert r.status_code == 200
    assert r.json()["count"] == 41


def test_get_one() -> None:
    r = client.get("/origins/2")
    assert r.status_code == 200
    assert r.json()["name"] == "Tarun Babbar"
    assert r.json()["project"].startswith("QAE2E")


def test_get_missing_returns_404() -> None:
    r = client.get("/origins/99")
    assert r.status_code == 404


def test_filter_by_tag_visual() -> None:
    r = client.get("/origins", params={"tag": "visual"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) >= 3  # Parity Scope, QA Coach, SpecCraft
    assert {o["project"] for o in body} >= {
        "Parity Scope",
        "Visual Regression QA Coach",
        "SpecCraft AI",
    }


def test_every_origin_serializes_via_api() -> None:
    """The full registry must round-trip through the API without error."""
    r = client.get("/origins")
    body = r.json()
    for item in body:
        Origin.model_validate(item)
