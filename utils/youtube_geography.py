from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

YOUTUBE_GEOGRAPHY_SNAPSHOT_COLLECTION = "youtube_analytics_snapshots"
YOUTUBE_GEOGRAPHY_SETTLED_LAG_DAYS = 3
YOUTUBE_GEOGRAPHY_AUTO_REFRESH_SECONDS = 15 * 60
YOUTUBE_GEOGRAPHY_BACKGROUND_REFRESH_SECONDS = 6 * 60 * 60
YOUTUBE_GEOGRAPHY_DEFAULT_EMPTY_MESSAGE = (
    "YouTube did not return geography data for this channel in the selected period."
)


def compute_youtube_settled_window(
    days: int,
    *,
    selected_end_date: date | None = None,
    lag_days: int = YOUTUBE_GEOGRAPHY_SETTLED_LAG_DAYS,
    reference_date: date | None = None,
) -> tuple[date, date, bool]:
    current_date = reference_date or datetime.now(timezone.utc).date()
    target_end_date = selected_end_date or current_date
    settled_end_date = current_date - timedelta(days=lag_days)
    effective_end_date = min(target_end_date, settled_end_date)
    effective_start_date = effective_end_date - timedelta(days=max(days - 1, 0))
    return effective_start_date, effective_end_date, effective_end_date != target_end_date


def normalize_youtube_geography_rows(
    rows: list[dict[str, Any]] | None,
    *,
    value_key: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows or []:
        country_code = str(row.get("country") or row.get("country_code") or "").upper()
        value = row.get(value_key)
        if not country_code or value in (None, ""):
            continue
        numeric_value = float(value)
        if numeric_value <= 0:
            continue
        normalized.append({
            "country_code": country_code,
            "count": int(numeric_value) if numeric_value.is_integer() else round(numeric_value, 4),
        })
    normalized.sort(key=lambda item: float(item.get("count") or 0), reverse=True)
    return normalized


async def store_youtube_geography_snapshot(
    db,
    *,
    account_id: str,
    user_id: str | None,
    channel_id: str | None,
    metric: str,
    window_days: int,
    rows: list[dict[str, Any]],
    effective_start_date: date,
    effective_end_date: date,
    fetched_at: datetime | None = None,
) -> None:
    if not rows:
        return
    refreshed_at = fetched_at or datetime.now(timezone.utc)
    await db[YOUTUBE_GEOGRAPHY_SNAPSHOT_COLLECTION].update_one(
        {
            "account_id": account_id,
            "platform": "youtube",
            "report_type": "geography",
            "metric": metric,
            "window_days": window_days,
            "as_of_date": effective_end_date.isoformat(),
        },
        {
            "$set": {
                "user_id": user_id,
                "channel_id": channel_id,
                "rows": rows,
                "top_rows": rows[:5],
                "total_row_count": len(rows),
                "effective_start_date": effective_start_date.isoformat(),
                "effective_end_date": effective_end_date.isoformat(),
                "last_refreshed_at": refreshed_at,
                "updated_at": refreshed_at,
            },
            "$setOnInsert": {
                "created_at": refreshed_at,
            },
        },
        upsert=True,
    )


async def load_latest_youtube_geography_snapshot(
    db,
    *,
    account_id: str,
    metric: str,
    window_days: int,
) -> dict[str, Any] | None:
    return await db[YOUTUBE_GEOGRAPHY_SNAPSHOT_COLLECTION].find_one(
        {
            "account_id": account_id,
            "platform": "youtube",
            "report_type": "geography",
            "metric": metric,
            "window_days": window_days,
        },
        sort=[("as_of_date", -1), ("last_refreshed_at", -1)],
    )


def build_youtube_geography_payload(
    *,
    rows: list[dict[str, Any]],
    metric_label: str,
    effective_start_date: date | str | None,
    effective_end_date: date | str | None,
    last_refreshed_at: datetime | str | None,
    source: str,
    provider_message: str | None = None,
    is_lag_adjusted: bool = False,
    is_snapshot_fallback: bool = False,
) -> dict[str, Any]:
    return {
        "rows": rows,
        "metric_label": metric_label,
        "effective_start_date": effective_start_date.isoformat() if hasattr(effective_start_date, "isoformat") else effective_start_date,
        "effective_end_date": effective_end_date.isoformat() if hasattr(effective_end_date, "isoformat") else effective_end_date,
        "last_refreshed_at": last_refreshed_at.isoformat() if hasattr(last_refreshed_at, "isoformat") else last_refreshed_at,
        "source": source,
        "provider_message": provider_message,
        "is_lag_adjusted": is_lag_adjusted,
        "is_snapshot_fallback": is_snapshot_fallback,
        "auto_refresh_seconds": YOUTUBE_GEOGRAPHY_AUTO_REFRESH_SECONDS,
    }


def merge_youtube_geography_payloads(
    payloads: list[dict[str, Any]],
    *,
    metric_label: str,
    empty_message: str = YOUTUBE_GEOGRAPHY_DEFAULT_EMPTY_MESSAGE,
) -> dict[str, Any]:
    merged: dict[str, float] = {}
    source = "empty"
    effective_start_date: str | None = None
    effective_end_date: str | None = None
    last_refreshed_at: str | None = None
    is_lag_adjusted = False
    provider_message = empty_message

    for payload in payloads:
        rows = payload.get("rows") or []
        payload_source = payload.get("source") or "empty"
        if rows:
            if payload_source == "live":
                source = "live"
            elif payload_source == "snapshot" and source != "live":
                source = "snapshot"
            effective_start_date = effective_start_date or payload.get("effective_start_date")
            effective_end_date = effective_end_date or payload.get("effective_end_date")
            last_refreshed_at = max(
                [value for value in [last_refreshed_at, payload.get("last_refreshed_at")] if value],
                default=last_refreshed_at,
            )
            is_lag_adjusted = is_lag_adjusted or bool(payload.get("is_lag_adjusted"))
        provider_message = payload.get("provider_message") or provider_message
        for row in rows:
            country_code = str(row.get("country_code") or "").upper()
            if not country_code:
                continue
            merged[country_code] = merged.get(country_code, 0) + float(row.get("count") or 0)

    merged_rows = [
        {
            "country_code": country_code,
            "count": int(value) if float(value).is_integer() else round(value, 4),
        }
        for country_code, value in sorted(merged.items(), key=lambda item: item[1], reverse=True)
    ]

    if not merged_rows:
        return build_youtube_geography_payload(
            rows=[],
            metric_label=metric_label,
            effective_start_date=effective_start_date,
            effective_end_date=effective_end_date,
            last_refreshed_at=last_refreshed_at,
            source="empty",
            provider_message=provider_message,
            is_lag_adjusted=is_lag_adjusted,
            is_snapshot_fallback=False,
        )

    return build_youtube_geography_payload(
        rows=merged_rows[:20],
        metric_label=metric_label,
        effective_start_date=effective_start_date,
        effective_end_date=effective_end_date,
        last_refreshed_at=last_refreshed_at,
        source=source,
        provider_message=None,
        is_lag_adjusted=is_lag_adjusted,
        is_snapshot_fallback=source == "snapshot",
    )
