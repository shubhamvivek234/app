"""Customer input cannot select fixtures or broaden an unsupported audience."""
from unittest.mock import AsyncMock

import httpx
import pytest

from outreach.core.search_sources import (
    SearchSourceError,
    classify_linkedin_source_url,
    parse_search_source,
    search_source_capabilities,
)
from outreach.engine.voyager_client import VoyagerClient
from outreach.models import OutreachLead
from outreach.core.search_sources import unverified_search_lead

URL = "https://www.linkedin.com/search/results/people/?keywords=Chief%20Officer"


@pytest.mark.parametrize("url", [
    "http://www.linkedin.com/search/results/people/?keywords=CEO",
    "https://linkedin.com.attacker.invalid/search/results/people/?keywords=CEO",
    "https://www.linkedin.com@attacker.invalid/search/results/people/?keywords=CEO",
    "https://name:password@www.linkedin.com/search/results/people/?keywords=CEO",
    "https://www.linkedin.com:443/search/results/people/?keywords=CEO",
    "/search/results/people/?keywords=CEO", "https://www.linkedin.com./search/results/people/?keywords=CEO",
    "https://www.linkedin.com/search/results/companies/?keywords=CEO",
    "https://www.linkedin.com/%73earch/results/people/?keywords=CEO",
    URL + "#fragment", URL + "&keywords=Other", URL + "&geoUrn=123", URL + "&network=F",
    URL + "&page=2", URL + "&unknown=", URL + "&query=CEO",
    "https://www.linkedin.com/sales/search/people?query=(filters:List())",
    "https://www.linkedin.com/talent/search?keywords=CEO",
    "https://www.linkedin.com/search/results/people/?keywords=%GG",
    "https://www.linkedin.com/search/results/people/?keywords=%FF",
    "https://www.linkedin.com/search/results/people/?keywords=%28CEO%29",
    "https://www.linkedin.com/search/results/people/?keywords=CEO%3AFounder",
    "https://www.linkedin.com/search/results/people/?keywords=CEO%2CFounder",
    "https://www.linkedin.com/search/results/people/?keywords=CEO%5CFounder",
    "https://www.linkedin.com/search/results/people/?keywords=%2528CEO%2529",
    "https://www.linkedin.com/search/results/people/?keywords=", URL + "\n&origin=FACETED_SEARCH",
])
def test_rejects_ambiguous_or_unsupported_search_input(url):
    with pytest.raises(SearchSourceError):
        parse_search_source(url)


def test_keyword_contract_preserves_meaning_and_drops_only_supported_tracking():
    parsed = parse_search_source(URL + "&origin=FACETED_SEARCH")
    assert parsed["keywords"] == "Chief Officer" and parsed["search_type"] == "basic"
    assert parsed["clean_url"] == URL


def test_normal_modeled_manual_contact_is_not_a_search_hold():
    lead = OutreachLead(workspace_id="w", campaign_id="c", linkedin_url="https://linkedin.com/in/person").model_dump()
    assert lead["import_job_id"] is None and lead["staged_at"] is None
    assert not unverified_search_lead(lead)


@pytest.mark.parametrize("live,mock", [("false", "false"), ("true", "false"), ("true", "true")])
def test_source_catalog_never_claims_unverified_collection_available(monkeypatch, live, mock):
    monkeypatch.setenv("OUTREACH_LIVE_ACTIONS_ENABLED", live)
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", mock)
    catalog = search_source_capabilities()
    assert catalog["contract_version"] == 1
    assert all(row["collection_available"] is False and row["reason"] for row in catalog["sources"])


def client(monkeypatch, payload):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "false")
    adapter = VoyagerClient(li_at="fixture-real-session", jsession_id="ajax:fixture", proxy_url="http://127.0.0.1:9")
    adapter._request = AsyncMock(return_value=httpx.Response(200, json=payload))
    return adapter


@pytest.mark.parametrize("keyword", ["short", "empty", "canary", "checkpoint", "rate_limit", "session_expired", "commercial_limit", "unresolvable"])
@pytest.mark.asyncio
async def test_nonmock_keywords_use_the_actual_transport_path(monkeypatch, keyword):
    adapter = client(monkeypatch, {"elements": [{"title": {"text": "Observed Person"},
        "navigationUrl": "https://www.linkedin.com/in/observed-person"}], "paging": {"total": 1}})
    result = await adapter.search_people_entities(URL.replace("Chief%20Officer", keyword))
    adapter._request.assert_awaited_once()
    assert result["entities"][0]["raw_name"] == "Observed Person"
    assert result["total_results"] == 1


@pytest.mark.parametrize("payload", [{}, [], {"elements": {}}, {"elements": []}, {"elements": [None]},
    {"elements": [], "paging": {"total": "100"}}, {"elements": [], "paging": {"total": True}},
    {"elements": [], "paging": {"total": -1}}, {"elements": [], "paging": {"total": 10}},
    {"elements": [], "paging": {"total": 0}, "metadata": {"totalResultCount": 2}},
    {"elements": [{"title": {"text": ""}, "name": 123}], "paging": {"total": 1}},
    {"elements": [], "paging": {"total": 0}, "errors": [{"message": "Denied"}]},
    {"elements": [], "paging": {"total": 0}, "error": {"message": "Denied"}},
    {"elements": [], "paging": {"total": 0}, "status": 403},
    {"elements": [], "paging": {"total": 0}, "statusCode": 500},
    {"elements": [], "paging": {"total": 0}, "status": "200"},
    {"elements": [], "paging": {"total": 0}, "status": True}])
@pytest.mark.asyncio
async def test_unknown_or_contradictory_schema_is_not_empty_success(monkeypatch, payload):
    adapter = client(monkeypatch, payload)
    with pytest.raises(SearchSourceError):
        await adapter.search_people_entities(URL)


@pytest.mark.asyncio
async def test_missing_total_stays_unknown_and_zero_is_not_replaced(monkeypatch):
    adapter = client(monkeypatch, {"elements": [{"name": "Observed Person", "navigationUrl": "https://www.linkedin.com/in/person"}]})
    assert (await adapter.search_people_entities(URL))["total_results"] is None
    adapter._request.return_value = httpx.Response(200, json={"elements": [], "paging": {"total": 0}})
    assert (await adapter.search_people_entities(URL))["total_results"] == 0


@pytest.mark.asyncio
async def test_mock_adapter_has_no_production_fixture_generator(monkeypatch):
    monkeypatch.setenv("OUTREACH_MOCK_AUTH", "true")
    adapter = VoyagerClient(li_at="mock_session")
    adapter._request = AsyncMock()
    with pytest.raises(SearchSourceError):
        await adapter.search_people_entities(URL)
    adapter._request.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_filter_denies_before_transport(monkeypatch):
    adapter = client(monkeypatch, {})
    with pytest.raises(SearchSourceError):
        await adapter.search_people_entities(URL + "&geoUrn=123")
    adapter._request.assert_not_awaited()


@pytest.mark.parametrize("status", [301, 302, 401, 403, 429, 500])
@pytest.mark.asyncio
async def test_failed_or_redirected_responses_do_not_report_zero(monkeypatch, status):
    adapter = client(monkeypatch, {})
    adapter._request.return_value = httpx.Response(status, json={})
    result = await adapter.search_people_entities(URL)
    assert result["total_results"] is None and result["stop_reason"]


@pytest.mark.parametrize("start,count", [(True, 1), (-1, 1), (1000, 1), (0, False), (0, 0), (0, 11)])
@pytest.mark.asyncio
async def test_invalid_bounds_deny_before_transport(monkeypatch, start, count):
    adapter = client(monkeypatch, {})
    with pytest.raises(SearchSourceError):
        await adapter.search_people_entities(URL, start=start, count=count)
    adapter._request.assert_not_awaited()


def test_classify_linkedin_source_url_covers_four_dripify_channels():
    # 1. Basic LinkedIn Search (100 pages * 10 = 1,000 max)
    basic = classify_linkedin_source_url("https://www.linkedin.com/search/results/people/?keywords=CEO")
    assert basic["is_valid"] is True
    assert basic["source_type"] == "basic"
    assert basic["max_profiles"] == 1000
    assert basic["max_pages"] == 100
    assert basic["page_size"] == 10
    assert basic["is_first_degree_batch"] is False

    # 1b. Basic Search with 1st-degree network=["F"] batching filter
    first_deg = classify_linkedin_source_url("https://www.linkedin.com/search/results/people/?network=%5B%22F%22%5D")
    assert first_deg["is_valid"] is True
    assert first_deg["source_type"] == "basic"
    assert first_deg["is_first_degree_batch"] is True
    assert first_deg["sub_source"] == "first_degree_search_batch"

    # 2. Sales Navigator Search & Saved List (99 pages * 25 = 2,500 max)
    sn = classify_linkedin_source_url("https://www.linkedin.com/sales/search/people?query=(filters:List())")
    assert sn["is_valid"] is True
    assert sn["source_type"] == "sales_nav"
    assert sn["max_profiles"] == 2500
    assert sn["max_pages"] == 99
    assert sn["page_size"] == 25

    # 3. LinkedIn Recruiter Search & Project Pipeline Tab (40 pages * 25 = 1,000 max)
    rec_search = classify_linkedin_source_url("https://www.linkedin.com/talent/hire/12345/discover/recruiterSearch")
    assert rec_search["is_valid"] is True
    assert rec_search["source_type"] == "recruiter"
    assert rec_search["sub_source"] == "talent_search"
    assert rec_search["max_profiles"] == 1000
    assert rec_search["max_pages"] == 40
    assert rec_search["page_size"] == 25
    assert "1990-2000" in rec_search["graduation_year_batches"]

    rec_pipe = classify_linkedin_source_url("https://www.linkedin.com/talent/hire/12345/manage/all/pipeline")
    assert rec_pipe["is_valid"] is True
    assert rec_pipe["source_type"] == "recruiter"
    assert rec_pipe["sub_source"] == "pipeline"
    assert rec_pipe["max_profiles"] == 1000

    # 4. My Network · Recent 1st-Degree Connections (1,000 max, most recent first)
    conn = classify_linkedin_source_url("https://www.linkedin.com/mynetwork/invite-connect/connections/")
    assert conn["is_valid"] is True
    assert conn["source_type"] == "connections"
    assert conn["max_profiles"] == 1000
    assert conn["sort_order"] == "most_recent_first"
    assert "network=%5B%22F%22%5D" in conn["batching_search_url"]

    # 5. LinkedIn Post Engagers (New badge, 500 max)
    post = classify_linkedin_source_url("https://www.linkedin.com/posts/acme-corp_b2b-growth-activity-7150000000000000000-abcd")
    assert post["is_valid"] is True
    assert post["source_type"] == "post"
    assert post["max_profiles"] == 500
    assert post["badge"] == "New"
    assert post["profiles_found_label"] == "500+"

    # 6. LinkedIn Group Members (2,500 max)
    group = classify_linkedin_source_url("https://www.linkedin.com/groups/1234567/")
    assert group["is_valid"] is True
    assert group["source_type"] == "group"
    assert group["max_profiles"] == 2500
    assert group["profiles_found_label"] == "2 500+"


def test_dripify_step3_lead_filter_rules_and_bracket_validation():
    from outreach.core.lead_importer import evaluate_lead_filter_rules
    from outreach.core.dag_compiler import find_unreplaced_brackets, contains_unreplaced_brackets
    from outreach.core.sequence_preview import analyze_sequence

    # 1. Step 3 Lead filtering rules
    rules = {
        "require_open_profile": True,
        "require_profile_photo": True,
        "min_connections_500": True,
        "exclude_free_account": True,
    }
    assert evaluate_lead_filter_rules({"is_open_profile": False}, rules)[0] == "filtered_not_open_profile"
    assert evaluate_lead_filter_rules({"is_open_profile": True, "has_photo": False}, rules)[0] == "filtered_no_photo"
    assert evaluate_lead_filter_rules(
        {"is_open_profile": True, "avatar_url": "https://img.example/a.jpg", "connections_count": 120},
        rules,
    )[0] == "filtered_under_500_connections"
    assert evaluate_lead_filter_rules(
        {
            "is_open_profile": True,
            "avatar_url": "https://img.example/a.jpg",
            "connections_count": 650,
            "profile_type": "free",
            "is_premium": False,
        },
        rules,
    )[0] == "filtered_free_account"
    assert evaluate_lead_filter_rules(
        {
            "is_open_profile": True,
            "avatar_url": "https://img.example/a.jpg",
            "connections_count": 650,
            "profile_type": "premium",
            "is_premium": True,
        },
        rules,
    ) == (None, None)

    # 2. Unreplaced [BRACKETS] detection (ignores AI prompt tokens ✨ [Prompt Name])
    raw_msg = "Hi {{first_name}}, I saw your post about [insert topic] and ✨ [Pain Point Hook] at [Your Company]."
    brackets = find_unreplaced_brackets(raw_msg)
    assert brackets == ["[insert topic]", "[Your Company]"]
    assert contains_unreplaced_brackets(raw_msg) is True
    assert contains_unreplaced_brackets("Hi {{first_name}}, ✨ [Pain Point Hook]!") is False

    # 3. Sequence analysis surfaces unreplaced_bracket_placeholder error
    from outreach.core.dag_compiler import DAGCompiler
    compiled = DAGCompiler.validate_and_compile(
        nodes=[
            {
                "id": "msg_1",
                "type": "send_message",
                "delay_hours": 0,
                "config": {"body": "Hi {{first_name}}, let's chat about [your pain point]!"},
            },
        ],
        edges=[],
    )
    analysis = analyze_sequence(compiled)
    codes = [item["code"] for item in analysis["issues"]]
    assert "unreplaced_bracket_placeholder" in codes
