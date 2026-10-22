"""Explicit test-only historical crawler fixtures; never imported by production."""
from urllib.parse import parse_qs, urlsplit
from outreach.models import SearchImportStopReason


def fixture_parser(url):
    keywords = parse_qs(urlsplit(url).query).get("keywords", [""])[0]
    sales = "/sales/" in url
    recruiter = "/talent/" in url
    connections = "/mynetwork/invite-connect/connections" in url
    search_type = (
        "sales_nav" if sales
        else "recruiter" if recruiter
        else "connections" if connections
        else "basic"
    )
    return {"is_valid": True, "is_sales_nav": sales, "is_recruiter": recruiter, "keywords": keywords,
            "search_type": search_type, "clean_url": url}


async def fixture_search(self, search_url, start=0, count=10):
    parsed = fixture_parser(search_url)
    is_sales_nav, keywords = parsed["is_sales_nav"], parsed["keywords"]
    if "empty" in keywords.lower() or "empty_canary" in search_url.lower():
        return {
            "entities": [],
            "total_results": 0,
            "stop_reason": SearchImportStopReason.SEARCH_EXHAUSTED,
            "user_error_message": "No matching leads found for this search URL.",
            "status_code": 200,
        }
    if "commercial_limit" in keywords.lower() or "commercial_limit_canary" in search_url.lower():
        return {
            "entities": [],
            "total_results": 0,
            "stop_reason": SearchImportStopReason.COMMERCIAL_USE_LIMIT,
            "user_error_message": "Monthly LinkedIn commercial search limit reached on this account. Upgrade to Sales Navigator or resume next month.",
            "status_code": 200,
        }
    if "rate_limit" in keywords.lower() or "rate_limit_canary" in search_url.lower():
        return {
            "entities": [],
            "total_results": 0,
            "stop_reason": SearchImportStopReason.RATE_LIMITED,
            "user_error_message": "LinkedIn rate limit reached. Pausing search import.",
            "status_code": 429,
        }
    if "checkpoint" in keywords.lower() or "checkpoint_canary" in search_url.lower():
        return {
            "entities": [],
            "total_results": 0,
            "stop_reason": SearchImportStopReason.CHECKPOINT,
            "user_error_message": "LinkedIn security checkpoint detected. Automation paused for your safety.",
            "status_code": 403,
        }
    if "session_expired" in keywords.lower() or "session_expired_canary" in search_url.lower():
        return {
            "entities": [],
            "total_results": 0,
            "stop_reason": SearchImportStopReason.SESSION_EXPIRED,
            "user_error_message": "LinkedIn session cookie expired. Reconnect the sender in Settings.",
            "status_code": 401,
        }

    # Generate mock search results
    total_mock = 50 if ("short_canary" in keywords.lower() or "short" in search_url.lower()) else 1000
    if start >= total_mock:
        return {
            "entities": [],
            "total_results": total_mock,
            "stop_reason": SearchImportStopReason.SEARCH_EXHAUSTED,
            "user_error_message": None,
            "status_code": 200,
        }

    page_len = min(count, total_mock - start)
    entities = []
    for i in range(page_len):
        idx = start + i + 1
        if ("unresolvable_canary" in keywords.lower() or "unresolvable" in search_url.lower()) and i == 0:
            entities.append({
                "raw_name": "LinkedIn Member",
                "first_name": "LinkedIn",
                "last_name": "Member",
                "job_title": "Out of Network Member",
                "company_name": "",
                "location": "",
                "headline": "LinkedIn Member",
                "profile_url": "",
                "vanity_name": None,
                "member_urn": None,
                "sales_lead_urn": None,
                "is_unresolvable": True,
            })
            continue

        lead_name = f"Alex Morgan {idx}" if not is_sales_nav else f"Sales Lead {idx}"
        vanity = f"alex-morgan-{idx}" if not is_sales_nav else f"sales-lead-{idx}"
        member_urn = f"urn:li:member:{200000 + idx}"
        sales_urn = f"urn:li:fs_salesProfile:(ACwAA{idx:06d},NAME_SEARCH)" if is_sales_nav else None

        entities.append({
            "raw_name": lead_name,
            "first_name": lead_name.split()[0],
            "last_name": lead_name.split()[-1],
            "job_title": "Director of Growth" if idx % 2 == 0 else "VP of Engineering",
            "company_name": "Tech Corp" if idx % 3 == 0 else "Innovate Labs",
            "location": "San Francisco, CA",
            "headline": f"{'Director of Growth' if idx % 2 == 0 else 'VP of Engineering'} at {'Tech Corp' if idx % 3 == 0 else 'Innovate Labs'}",
            "profile_url": f"https://www.linkedin.com/in/{vanity}",
            "vanity_name": vanity,
            "member_urn": member_urn,
            "sales_lead_urn": sales_urn,
            "is_unresolvable": False,
        })

    return {
        "entities": entities,
        "total_results": total_mock,
        "stop_reason": None,
        "user_error_message": None,
        "status_code": 200,
    }
