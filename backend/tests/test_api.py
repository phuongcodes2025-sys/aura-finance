import itertools
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app.advisor import AISettings
from app.database import Database
from app.impact import EVENTS, RULES, analyze
from app.main import create_app
from app.seed import main as seed_main, seed_demo
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


V1_PROFILE = {
    "name": "Sarah",
    "occupation": "Nail Salon Owner",
    "income_range": "75k-100k",
    "business_owner": True,
    "stocks": ["NVDA", "AAPL"],
    "properties": [{"property_type": "Rental Property", "property_count": 2}],
}


def v1_analysis(client, profile=V1_PROFILE):
    response = client.post("/api/v1/profile", json=profile)
    assert response.status_code == 201
    user_id = response.json()["id"]
    response = client.post("/api/v1/analyze", json={"user_id": user_id, "event_id": 2})
    assert response.status_code == 201
    return user_id, response.json()


def test_versioned_profile_and_dashboard_flow(client):
    user_id, analysis = v1_analysis(client)
    profile = client.get(f"/api/v1/profile/{user_id}").json()
    for key, value in V1_PROFILE.items():
        assert profile[key] == value
    assert profile["investor"] and profile["property_owner"]
    assert "created_at" in profile and "createdAt" not in profile
    assert analysis["business"]["risk"] == "High"
    assert analysis["real_estate"]["risk"] == "Moderate"
    assert "fixed-rate" in analysis["real_estate"]["explanation"]
    assert len(analysis["recommendations"]) >= 3
    assert analysis["recommendation_source"] == "rules"
    assert analysis["overall_summary"]
    saved = client.get(f"/api/v1/analyze/{analysis['analysis_id']}")
    assert saved.status_code == 200 and saved.json() == analysis
    dashboard = client.get(f"/api/v1/dashboard/{analysis['analysis_id']}").json()
    assert dashboard["profile"] == profile
    assert dashboard["event"] == client.get("/api/v1/events/2").json()
    assert dashboard["analysis"] == analysis
    assert dashboard["recommendations"] == analysis["recommendations"]
    legacy = client.get(f"/api/analysis/{analysis['analysis_id']}").json()
    assert legacy["profile"]["stocks"] == V1_PROFILE["stocks"]
    assert legacy["profile"]["properties"][0]["propertyCount"] == 2
    assert legacy["recommendations"] == analysis["recommendations"]


def test_versioned_events_preserve_ids(client):
    events = client.get("/api/v1/events").json()
    assert len(events) == 5
    assert [event["id"] for event in events] == [1, 2, 3, 4, 5]
    for event in events:
        assert client.get(f"/api/v1/events/{event['id']}").json() == event
        assert client.get(f"/api/events/{event['id']}").json()["title"] == event["event_name"]
        assert event["summary"]


@pytest.mark.parametrize("change", [
    {"name": " "}, {"occupation": "\n"}, {"income_range": "unknown"},
    {"business_owner": "yes"}, {"stocks": [""]}, {"stocks": [" NVDA"]},
    {"stocks": ["A" * 11]}, {"stocks": ["NVDA", "nvda"]},
    {"stocks": [100]}, {"stocks": ["<script>"]}, {"stocks": None},
    {"properties": [{"property_type": "Rental", "property_count": 0}]},
    {"properties": [{"property_type": "Rental", "property_count": True}]},
    {"properties": [{"property_type": " ", "property_count": 2}]},
    {"properties": None}, {"unexpected": True}, {"incomeRange": "60k-100k"},
])
def test_invalid_versioned_profiles(client, change):
    assert client.post("/api/v1/profile", json={**V1_PROFILE, **change}).status_code == 422


def test_ticker_normalization_and_property_trimming(client):
    response = client.post("/api/v1/profile", json={
        **V1_PROFILE, "stocks": ["nvda", "BRK.B"],
        "properties": [{"property_type": " Rental ", "property_count": 2}],
    })
    assert response.status_code == 201
    profile = client.get(f"/api/v1/profile/{response.json()['id']}").json()
    assert profile["stocks"] == ["NVDA", "BRK.B"]
    assert profile["properties"][0]["property_type"] == "Rental"


def test_profile_updates_preserve_snapshots(client):
    user_id, analysis = v1_analysis(client)
    original_dashboard = client.get(f"/api/v1/dashboard/{analysis['analysis_id']}").json()
    response = client.patch(f"/api/v1/profile/{user_id}", json={"income_range": "100k-125k"})
    assert response.status_code == 200
    assert response.json()["income_range"] == "100k-125k"
    assert response.json()["stocks"] == V1_PROFILE["stocks"]
    response = client.patch(f"/api/v1/profile/{user_id}", json={
        "stocks": ["msft"], "properties": [],
    })
    assert response.status_code == 200
    assert response.json()["stocks"] == ["MSFT"]
    assert response.json()["investor"] is True
    assert response.json()["properties"] == []
    assert response.json()["property_owner"] is False
    response = client.patch(f"/api/v1/profile/{user_id}", json={"stocks": []})
    assert response.status_code == 200
    assert not response.json()["investor"]
    assert client.get(f"/api/v1/dashboard/{analysis['analysis_id']}").json() == original_dashboard
    assert client.get(f"/api/v1/analyze/{analysis['analysis_id']}").json() == analysis
    new = client.post("/api/v1/analyze", json={"user_id": user_id, "event_id": 2}).json()
    assert new["investments"]["risk"] == new["real_estate"]["risk"] == "Not applicable"
    assert len(new["recommendations"]) >= 3
    history = client.get(f"/api/v1/profile/{user_id}/analyses").json()
    assert [item["analysis_id"] for item in history] == [new["analysis_id"], analysis["analysis_id"]]


def test_put_replaces_profile_and_patch_is_partial(client):
    user_id, _ = v1_analysis(client)
    partial = client.put(f"/api/v1/profile/{user_id}", json={"income_range": "100k-125k"})
    assert partial.status_code == 422
    response = client.put(f"/api/v1/profile/{user_id}", json={
        "name": "New demo", "occupation": "Teacher", "income_range": "30k-60k",
    })
    assert response.status_code == 200
    assert response.json() == {"message": "Profile updated"}
    profile = client.get(f"/api/v1/profile/{user_id}").json()
    assert profile["name"] == "New demo"
    assert not profile["business_owner"] and not profile["investor"] and not profile["property_owner"]
    assert profile["stocks"] == [] and profile["properties"] == []


@pytest.mark.parametrize("body", [
    {}, {"name": None}, {"stocks": None}, {"properties": None},
    {"stocks": ["NVDA", "nvda"]}, {"income_range": "unknown"},
    {"properties": [{"property_type": "Rental", "property_count": -1}]},
    {"user_id": 99},
])
def test_invalid_versioned_updates_are_atomic(client, body):
    user_id, _ = v1_analysis(client)
    original = client.get(f"/api/v1/profile/{user_id}").json()
    assert client.patch(f"/api/v1/profile/{user_id}", json=body).status_code == 422
    assert client.get(f"/api/v1/profile/{user_id}").json() == original


def test_legacy_profile_updates_history_and_dashboard(client):
    original = saved_analysis(client)
    user_id = original["profile"]["id"]
    response = client.patch(f"/api/profile/{user_id}", json={
        "occupation": " Teacher ", "businessOwner": False,
    })
    assert response.status_code == 200
    assert response.json()["occupation"] == "Teacher"
    assert not response.json()["businessOwner"]
    assert client.get(f"/api/analysis/{original['id']}").json() == original
    dashboard = client.get(f"/api/dashboard/{original['id']}").json()
    assert dashboard["analysis"] == original
    assert dashboard["profile"] == original["profile"]
    history = client.get(f"/api/profile/{user_id}/analyses").json()
    assert history == [{
        "analysisId": original["id"], "event": original["event"]["title"],
        "createdAt": original["createdAt"],
    }]
    assert client.patch(f"/api/profile/{user_id}", json={}).status_code == 422
    assert client.patch(f"/api/profile/{user_id}", json={"occupation": None}).status_code == 422


def test_legacy_exposure_updates_cannot_contradict_holdings(client):
    user_id, _ = v1_analysis(client)
    for field in ("investor", "propertyOwner"):
        response = client.patch(f"/api/profile/{user_id}", json={field: False})
        assert response.status_code == 409
    profile = client.get(f"/api/v1/profile/{user_id}").json()
    assert profile["stocks"] == V1_PROFILE["stocks"]
    assert profile["properties"] == V1_PROFILE["properties"]


@pytest.mark.parametrize("path", [
    "/api/events/99", "/api/v1/events/99", "/api/v1/profile/99",
    "/api/profile/99/analyses", "/api/v1/profile/99/analyses",
    "/api/v1/analyze/99", "/api/dashboard/99", "/api/v1/dashboard/99",
    "/api/chat/99", "/api/v1/chat/99",
])
def test_missing_new_resources(client, path):
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", [
    "/api/events/0", "/api/v1/events/-1", "/api/v1/profile/invalid",
    "/api/profile/0/analyses", "/api/v1/profile/0/analyses",
    "/api/v1/analyze/0", "/api/dashboard/0", "/api/v1/dashboard/0",
    "/api/chat/0", "/api/v1/chat/0",
])
def test_invalid_new_resource_ids(client, path):
    assert client.get(path).status_code == 422


def test_empty_histories_and_isolation(client):
    first = client.post("/api/v1/profile", json=V1_PROFILE).json()["id"]
    assert client.get(f"/api/v1/profile/{first}/analyses").json() == []
    second, analysis = v1_analysis(client)
    assert client.get(f"/api/v1/profile/{first}/analyses").json() == []
    assert len(client.get(f"/api/v1/profile/{second}/analyses").json()) == 1
    assert client.get(f"/api/v1/chat/{analysis['analysis_id']}").json() == []


def test_versioned_chat_and_legacy_chat_share_persisted_history(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "Consider reviewing loan terms. Educational, not financial advice."}}]})

    with provider_client(tmp_path, monkeypatch, handler) as client:
        user_id, analysis = v1_analysis(client)
        analysis_id = analysis["analysis_id"]
        response = client.post("/api/v1/chat", json={
            "user_id": user_id, "analysis_id": analysis_id, "message": "How do rates affect loans?",
        })
        assert response.status_code == 200 and response.json()["source"] == "ai"
        first_answer = response.json()["response"]
        response = client.post("/api/chat", json={"analysisId": analysis_id, "question": "What about fixed rates?"})
        assert response.status_code == 200
        history = client.get(f"/api/v1/chat/{analysis_id}").json()
        assert [item["role"] for item in history] == ["user", "assistant", "user", "assistant"]
        assert history[1]["message"] == first_answer
        assert history[3]["message"] == response.json()["answer"]
        assert all(item["user_id"] == user_id and item["analysis_id"] == analysis_id for item in history)
        assert [item["id"] for item in history] == sorted(item["id"] for item in history)
        legacy = client.get(f"/api/chat/{analysis_id}").json()
        assert [item["message"] for item in legacy] == [item["message"] for item in history]
    with TestClient(create_app(str(tmp_path / "ai.sqlite3"), NO_AI)) as restarted:
        assert restarted.get(f"/api/v1/chat/{analysis_id}").json() == history
        assert restarted.get(f"/api/v1/analyze/{analysis_id}").json() == analysis
        assert restarted.get(f"/api/v1/profile/{user_id}").json()["stocks"] == V1_PROFILE["stocks"]
    for payload in calls:
        context = payload["messages"][1]["content"]
        assert "NVDA" not in context and "Sarah" not in context
        assert '"stocks"' not in context and '"properties"' not in context
        assert "Interest rate increase" in context


def test_chat_profile_mismatch_does_not_call_ai(tmp_path, monkeypatch):
    def handler(request):
        pytest.fail("A mismatched analysis/profile must not reach the AI provider")

    with provider_client(tmp_path, monkeypatch, handler) as client:
        _, analysis = v1_analysis(client)
        other_id = client.post("/api/v1/profile", json=V1_PROFILE).json()["id"]
        response = client.post("/api/v1/chat", json={
            "user_id": other_id, "analysis_id": analysis["analysis_id"], "message": "Why?",
        })
        assert response.status_code == 404
        assert client.get(f"/api/v1/chat/{analysis['analysis_id']}").json() == []


def test_failed_chat_does_not_save_success_shaped_history(client):
    user_id, analysis = v1_analysis(client)
    response = client.post("/api/v1/chat", json={
        "user_id": user_id, "analysis_id": analysis["analysis_id"], "message": "Why?",
    })
    assert response.status_code == 503
    assert "response" not in response.json()
    assert client.get(f"/api/v1/chat/{analysis['analysis_id']}").json() == []


def test_provider_failure_leaves_history_unchanged(tmp_path, monkeypatch):
    with provider_client(tmp_path, monkeypatch, lambda request: httpx.Response(429)) as client:
        user_id, analysis = v1_analysis(client)
        response = client.post("/api/v1/chat", json={
            "user_id": user_id, "analysis_id": analysis["analysis_id"], "message": "Why?",
        })
        assert response.status_code == 502
        assert client.get(f"/api/v1/chat/{analysis['analysis_id']}").json() == []


@pytest.mark.parametrize("prefix", ["/api", "/api/v1"])
def test_profile_delete_cleans_dependents_and_preserves_other_users(tmp_path, prefix):
    path = str(tmp_path / "delete.sqlite3")
    with TestClient(create_app(path, NO_AI)) as client:
        user_id, analysis = v1_analysis(client)
        other_id, other_analysis = v1_analysis(client)
        Database(path).save_chat(
            analysis["analysis_id"], user_id, "Why?", "Educational reply", analysis["created_at"],
        )
        response = client.delete(f"{prefix}/profile/{user_id}")
        assert response.status_code == 200
        assert response.json() == {"message": "Profile deleted"}
        assert client.get(f"/api/v1/profile/{user_id}").status_code == 404
        assert client.get(f"/api/v1/analyze/{analysis['analysis_id']}").status_code == 404
        assert client.get(f"/api/v1/chat/{analysis['analysis_id']}").status_code == 404
        assert client.delete(f"{prefix}/profile/{user_id}").status_code == 404
        assert client.get(f"/api/v1/profile/{other_id}").status_code == 200
        assert client.get(f"/api/v1/analyze/{other_analysis['analysis_id']}").json() == other_analysis
        assert len(client.get("/api/events").json()) == 5
    with sqlite3.connect(path) as connection:
        for table in ("stocks", "properties", "chat_messages"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (user_id,)).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM recommendations WHERE analysis_id=?", (analysis["analysis_id"],),
        ).fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_existing_database_backfills_recommendations_idempotently(tmp_path):
    path = str(tmp_path / "old.sqlite3")
    with TestClient(create_app(path, NO_AI)) as client:
        result = saved_analysis(client)
    old_result = {
        key: value for key, value in result.items()
        if key not in ("overallSummary", "recommendations", "recommendationSource")
    }
    old_result["profile"].pop("stocks")
    old_result["profile"].pop("properties")
    with sqlite3.connect(path) as connection:
        for table in ("stocks", "properties", "recommendations", "chat_messages"):
            connection.execute(f"DROP TABLE {table}")
        connection.execute(
            "UPDATE analysis_results SET result_json=? WHERE id=?",
            (json.dumps(old_result), result["id"]),
        )
    for _ in range(2):
        with TestClient(create_app(path, NO_AI)) as client:
            upgraded = client.get(f"/api/analysis/{result['id']}").json()
            assert upgraded["impacts"] == old_result["impacts"]
            assert upgraded["profile"]["stocks"] == []
            assert upgraded["profile"]["properties"] == []
            assert upgraded["overallSummary"]
            assert len(upgraded["recommendations"]) >= 3
            assert upgraded["createdAt"] == old_result["createdAt"]
    with sqlite3.connect(path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
        assert count == len(upgraded["recommendations"])
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_demo_seed_persists_sarah_and_analysis(tmp_path):
    path = str(tmp_path / "demo.sqlite3")
    user_id, analysis_id = seed_demo(Database(path))
    with TestClient(create_app(path, NO_AI)) as client:
        profile = client.get(f"/api/v1/profile/{user_id}").json()
        for key, value in V1_PROFILE.items():
            assert profile[key] == value
        dashboard = client.get(f"/api/v1/dashboard/{analysis_id}").json()
        assert dashboard["event"]["id"] == 2
        assert dashboard["analysis"]["business"]["risk"] == "High"
        assert len(dashboard["recommendations"]) >= 3


@pytest.mark.parametrize("income_range", [
    "under-30k", "30k-60k", "60k-100k", "over-100k", "75k-100k", "100k-125k",
])
@pytest.mark.parametrize("event", EVENTS, ids=lambda event: event.title)
def test_versioned_events_and_ranges_without_holdings(client, income_range, event):
    response = client.post("/api/v1/profile", json={
        "name": "Demo", "occupation": "Teacher", "income_range": income_range,
    })
    assert response.status_code == 201
    response = client.post("/api/v1/analyze", json={
        "user_id": response.json()["id"], "event_id": event.id,
    })
    assert response.status_code == 201
    analysis = response.json()
    for area in ("business", "investments", "real_estate"):
        assert analysis[area]["risk"] == "Not applicable"
    assert len(analysis["recommendations"]) >= 3
    assert analysis["recommendation_source"] == "rules"


@pytest.mark.parametrize("body", [
    {"user_id": True, "event_id": 2},
    {"user_id": 0, "event_id": 2},
    {"user_id": 1, "event_id": "2"},
])
def test_invalid_versioned_analysis_ids(client, body):
    assert client.post("/api/v1/analyze", json=body).status_code == 422


def test_missing_versioned_mutations(client):
    assert client.post("/api/v1/analyze", json={"user_id": 99, "event_id": 2}).status_code == 404
    user_id = client.post("/api/v1/profile", json=V1_PROFILE).json()["id"]
    assert client.post("/api/v1/analyze", json={"user_id": user_id, "event_id": 99}).status_code == 404
    assert client.patch("/api/v1/profile/99", json={"name": "Demo"}).status_code == 404
    assert client.put("/api/v1/profile/99", json=V1_PROFILE).status_code == 404
    assert client.delete("/api/v1/profile/99").status_code == 404
    assert client.patch("/api/profile/99", json={"name": "Demo"}).status_code == 404


@pytest.mark.parametrize("change", [
    {"user_id": True}, {"analysis_id": 0}, {"message": " "},
    {"message": "a" * 1001}, {"role": "assistant"},
])
def test_invalid_versioned_chat(client, change):
    user_id, analysis = v1_analysis(client)
    request = {
        "user_id": user_id, "analysis_id": analysis["analysis_id"], "message": "Why?",
        **change,
    }
    assert client.post("/api/v1/chat", json=request).status_code == 422
    assert client.get(f"/api/v1/chat/{analysis['analysis_id']}").json() == []


def test_profile_deleted_during_provider_request_does_not_return_success(tmp_path, monkeypatch):
    user_ids = []

    def handler(request):
        Database(str(tmp_path / "ai.sqlite3")).delete_profile(user_ids[0])
        return httpx.Response(200, json={"choices": [{"message": {"content": "Educational answer"}}]})

    with provider_client(tmp_path, monkeypatch, handler) as client:
        user_id, analysis = v1_analysis(client)
        user_ids.append(user_id)
        response = client.post("/api/v1/chat", json={
            "user_id": user_id, "analysis_id": analysis["analysis_id"], "message": "Why?",
        })
        assert response.status_code == 404
        assert "response" not in response.json()
    with sqlite3.connect(str(tmp_path / "ai.sqlite3")) as connection:
        assert connection.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0] == 0


def test_chat_rejects_a_reused_analysis_id(tmp_path, monkeypatch):
    ids = []

    def handler(request):
        database = Database(str(tmp_path / "ai.sqlite3"))
        database.delete_profile(ids[0])
        from app.v1_schemas import ProfileCreate

        new_profile = database.create_profile(ProfileCreate.model_validate(V1_PROFILE).profile_data())
        new_analysis = database.create_analysis(new_profile.id, 2)
        assert new_profile.id == ids[0] and new_analysis.id == ids[1]
        return httpx.Response(200, json={"choices": [{"message": {"content": "Old scenario answer"}}]})

    with provider_client(tmp_path, monkeypatch, handler) as client:
        user_id, analysis = v1_analysis(client)
        ids.extend([user_id, analysis["analysis_id"]])
        response = client.post("/api/v1/chat", json={
            "user_id": user_id, "analysis_id": analysis["analysis_id"], "message": "Why?",
        })
        assert response.status_code == 404
        assert client.get(f"/api/v1/chat/{analysis['analysis_id']}").json() == []


def test_seed_command_uses_explicit_database(tmp_path, monkeypatch, capsys):
    path = tmp_path / "command.sqlite3"
    monkeypatch.setattr("sys.argv", ["seed", "--database", str(path)])
    seed_main()
    output = capsys.readouterr().out
    assert "Created demo profile 1 and analysis 1." in output
    assert "/api/v1/dashboard/1" in output
    assert Database(str(path)).profile(1).name == "Sarah"


def test_openapi_exposes_both_contracts(client):
    schema = client.get("/openapi.json").json()
    assert "/api/profile" in schema["paths"]
    assert "/api/v1/profile" in schema["paths"]
    assert "/api/v1/dashboard/{analysis_id}" in schema["paths"]
    request_schema = schema["paths"]["/api/v1/profile"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    component = schema["components"]["schemas"][request_schema["$ref"].split("/")[-1]]
    assert "income_range" in component["properties"]
    assert "incomeRange" not in component["properties"]
    assert client.get("/docs").status_code == 200
