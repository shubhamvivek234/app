from datetime import date, datetime, timezone

from utils.youtube_geography import (
    build_youtube_geography_payload,
    compute_youtube_settled_window,
    merge_youtube_geography_payloads,
    normalize_youtube_geography_rows,
)


def test_compute_youtube_settled_window_applies_lag_to_selected_end_date():
    start_date, end_date, is_lag_adjusted = compute_youtube_settled_window(
        30,
        selected_end_date=date(2026, 5, 24),
        lag_days=3,
        reference_date=date(2026, 5, 24),
    )

    assert start_date == date(2026, 4, 22)
    assert end_date == date(2026, 5, 21)
    assert is_lag_adjusted is True


def test_normalize_youtube_geography_rows_keeps_positive_country_counts():
    rows = normalize_youtube_geography_rows(
        [
            {"country": "in", "views": 5},
            {"country": "us", "views": 0},
            {"country": "", "views": 10},
            {"country": "gb", "views": 2.5},
        ],
        value_key="views",
    )

    assert rows == [
        {"country_code": "IN", "count": 5},
        {"country_code": "GB", "count": 2.5},
    ]


def test_merge_youtube_geography_payloads_prefers_live_rows_and_aggregates_counts():
    payload = merge_youtube_geography_payloads(
        [
            build_youtube_geography_payload(
                rows=[{"country_code": "IN", "count": 3}],
                metric_label="Views",
                effective_start_date="2026-04-22",
                effective_end_date="2026-05-21",
                last_refreshed_at=datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc),
                source="snapshot",
                provider_message=None,
                is_lag_adjusted=True,
                is_snapshot_fallback=True,
            ),
            build_youtube_geography_payload(
                rows=[
                    {"country_code": "IN", "count": 2},
                    {"country_code": "US", "count": 4},
                ],
                metric_label="Views",
                effective_start_date="2026-04-22",
                effective_end_date="2026-05-21",
                last_refreshed_at=datetime(2026, 5, 24, 15, 0, tzinfo=timezone.utc),
                source="live",
                provider_message=None,
                is_lag_adjusted=True,
                is_snapshot_fallback=False,
            ),
        ],
        metric_label="Views",
    )

    assert payload["source"] == "live"
    assert payload["is_snapshot_fallback"] is False
    assert payload["is_lag_adjusted"] is True
    assert payload["rows"] == [
        {"country_code": "IN", "count": 5},
        {"country_code": "US", "count": 4},
    ]
