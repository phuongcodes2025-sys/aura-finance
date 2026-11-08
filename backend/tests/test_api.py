import itertools
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.advisor import AISettings
from app.impact import EVENTS, RULES, analyze
from app.main import create_app
from app.schemas import Profile

PROFILE = {
    "name": "Dallas demo",
    "occupation": "Small business owner",
    "incomeRange": "60k-100k",
    "businessOwner": True,
    "investor": True,
    "propertyOwner": True,
}
NO_AI = AISettings("", "https://api.example.test/v1", "demo-model")


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(str(tmp_path / "test.sqlite3"), NO_AI)) as test_client:
        yield test_client


def saved_analysis(client):
    profile = client.post("/api/profile", json=PROFILE)
    assert profile.status_code == 201
    response = client.post("/api/analyze", json={"userId": profile.json()["id"], "eventId": 2})
    assert response.status_code == 201
    return response.json()


def test_health_events_and_rule_count(client):
    assert client.get("/api/health").json() == {"status": "ok", "aiConfigured": False}
    events = client.get("/api/events").json()
    assert len(events) == 5
    assert [event["id"] for event in events] == [1, 2, 3, 4, 5]
    assert len(RULES) == 10
    assert len({rule.id for rule in RULES}) == 10


@pytest.mark.parametrize("event", EVENTS, ids=lambda event: event.title)
@pytest.mark.parametrize("flags", list(itertools.product([False, True], repeat=3)))
@pytest.mark.parametrize("income_range", ["under-30k", "30k-60k", "60k-100k", "over-100k"])
def test_all_events_profiles_and_income_ranges(event, flags, income_range):
    profile = Profile(
        **{**PROFILE, "businessOwner": flags[0], "investor": flags[1],
           "propertyOwner": flags[2], "incomeRange": income_range},
        id=1, createdAt="2026-01-01T00:00:00+00:00",
    )
    result = analyze(profile, event)
    assert [impact.area for impact in result] == ["income", "business", "investments", "realEstate"]
    assert result == analyze(profile, event)
    for impact, active in zip(result, (True, *flags)):
        assert (impact.risk != "notApplicable") == active
        assert bool(impact.rule_id) == active
        assert bool(impact.considerations) == active
        assert impact.summary and impact.explanation


def test_profile_analysis_snapshot_and_restart(tmp_path):
    path = str(tmp_path / "persist.sqlite3")
    with TestClient(create_app(path, NO_AI)) as client:
        result = saved_analysis(client)
        assert len(result["impacts"]) == 4
        assert result["impacts"][1]["risk"] == "high"
        assert result["impacts"][3]["risk"] == "moderate"
        assert "fixed-rate" in result["impacts"][3]["explanation"]
        assert len(result["assumptions"]) == 4
        assert result["profile"]["occupation"] == PROFILE["occupation"]
        assert result["event"]["id"] == 2
    with TestClient(create_app(path, NO_AI)) as restarted:
        assert restarted.get(f"/api/analysis/{result['id']}").json() == result
        assert len(restarted.get("/api/events").json()) == 5


def test_profile_retrieval_and_restart(tmp_path):
    path = str(tmp_path / "profile.sqlite3")
    with TestClient(create_app(path, NO_AI)) as client:
        response = client.post("/api/profile", json={**PROFILE, "name": " Sarah "})
        assert response.status_code == 201
        profile = response.json()
        assert profile["name"] == "Sarah"
        assert client.get(f"/api/profile/{profile['id']}").json() == profile
    with TestClient(create_app(path, NO_AI)) as restarted:
        response = restarted.get(f"/api/profile/{profile['id']}")
        assert response.status_code == 200
        assert response.json() == profile


def test_profile_not_found(client):
    response = client.get("/api/profile/99")
    assert response.status_code == 404
    assert response.json() == {"detail": "Profile not found"}


@pytest.mark.parametrize("user_id", ["0", "-1", "invalid", "1.5"])
def test_invalid_profile_path(client, user_id):
    assert client.get(f"/api/profile/{user_id}").status_code == 422


def test_models_compatibility_import():
    from app.models import Profile as LegacyProfile

    assert LegacyProfile is Profile


def test_federal_reserve_event_reuses_interest_rate_rules(client):
    profile_id = client.post("/api/profile", json=PROFILE).json()["id"]
    rate_analysis = client.post(
        "/api/analyze", json={"userId": profile_id, "eventId": 2},
    )
    fed_analysis = client.post(
        "/api/analyze", json={"userId": profile_id, "eventId": 5},
    )
    assert rate_analysis.status_code == fed_analysis.status_code == 201
    assert fed_analysis.json()["impacts"] == rate_analysis.json()["impacts"]


@pytest.mark.parametrize("change", [
    {"occupation": ""}, {"occupation": "   "}, {"name": "\n"},
    {"occupation": "a" * 101}, {"incomeRange": "unknown"},
    {"businessOwner": "false"}, {"investor": 1}, {"unexpected": True},
])
def test_invalid_profiles(client, change):
    assert client.post("/api/profile", json={**PROFILE, **change}).status_code == 422


def test_sql_parameterization(client):
    response = client.post("/api/profile", json={**PROFILE, "occupation": "Developer'); DROP TABLE users; --"})
    assert response.status_code == 201
    assert client.post("/api/profile", json=PROFILE).status_code == 201


def test_no_exposures(client):
    response = client.post("/api/profile", json={
        **PROFILE, "businessOwner": False, "investor": False, "propertyOwner": False,
    })
    result = client.post("/api/analyze", json={"userId": response.json()["id"], "eventId": 1}).json()
    assert [item["risk"] for item in result["impacts"]] == ["high", "notApplicable", "notApplicable", "notApplicable"]


def test_missing_records_and_invalid_ids(client):
    assert client.post("/api/analyze", json={"userId": 100, "eventId": 1}).status_code == 404
    profile_id = client.post("/api/profile", json=PROFILE).json()["id"]
    assert client.post("/api/analyze", json={"userId": profile_id, "eventId": 99}).status_code == 404
    assert client.post("/api/analyze", json={"userId": profile_id, "eventId": 0}).status_code == 422
    assert client.post("/api/analyze", json={"userId": True, "eventId": 1}).status_code == 422
    assert client.get("/api/analysis/99").status_code == 404
    assert client.post("/api/chat", json={"analysisId": 99, "question": "Why?"}).status_code == 404
    assert client.post("/api/chat", json={"question": "Why?"}).status_code == 422


@pytest.mark.parametrize("question", ["", " \n ", "a" * 1001])
def test_invalid_chat_question(client, question):
    result = saved_analysis(client)
    assert client.post("/api/chat", json={"analysisId": result["id"], "question": question}).status_code == 422


def test_unconfigured_ai_is_explicit(client):
    result = saved_analysis(client)
    response = client.post("/api/chat", json={"analysisId": result["id"], "question": "Why?"})
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
    assert "answer" not in response.json()


def provider_client(tmp_path, monkeypatch, handler):
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "app.advisor.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    settings = AISettings("test-only-key", "https://api.example.test/v1", "test-model")
    return TestClient(create_app(str(tmp_path / "ai.sqlite3"), settings))


def test_ai_receives_saved_analysis_and_question(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Higher rates can affect variable-rate loans. Educational, not financial advice."}}]})

    with provider_client(tmp_path, monkeypatch, handler) as client:
        assert client.get("/api/health").json()["aiConfigured"] is True
        result = saved_analysis(client)
        response = client.post("/api/chat", json={"analysisId": result["id"], "question": "Why is my business high attention?"})
        assert response.status_code == 200
        assert response.json()["source"] == "ai"
    assert len(calls) == 1
    assert str(calls[0].url) == "https://api.example.test/v1/chat/completions"
    payload = json.loads(calls[0].content)
    assert payload["model"] == "test-model"
    context = payload["messages"][1]["content"]
    assert "Interest rate increase" in context
    assert "business-costs" in context
    assert "Why is my business" in context
    assert "Dallas demo" not in context
    assert "Do not calculate" in payload["messages"][0]["content"]


@pytest.mark.parametrize("body", [
    {}, {"choices": []}, {"choices": None},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": {"content": " "}}]},
])
def test_malformed_provider_response(tmp_path, monkeypatch, body):
    with provider_client(tmp_path, monkeypatch, lambda request: httpx.Response(200, json=body)) as client:
        result = saved_analysis(client)
        response = client.post("/api/chat", json={"analysisId": result["id"], "question": "Why?"})
        assert response.status_code == 502
        assert "answer" not in response.json()


@pytest.mark.parametrize("failure,expected_status", [("timeout", 504), ("connection", 502), ("rate_limit", 502)])
def test_provider_failures(tmp_path, monkeypatch, failure, expected_status):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("test timeout", request=request)
        if failure == "connection":
            raise httpx.ConnectError("test connection error", request=request)
        return httpx.Response(429, json={"error": "provider-private-error"})

    with provider_client(tmp_path, monkeypatch, handler) as client:
        result = saved_analysis(client)
        response = client.post("/api/chat", json={"analysisId": result["id"], "question": "Why?"})
        assert response.status_code == expected_status
        assert "provider-private-error" not in response.text
        assert "answer" not in response.json()
