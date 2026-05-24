from datetime import datetime, timezone

import pytest

from utils.timeslots import (
    find_next_available_timeslot,
    normalize_timeslot_category,
    normalize_timeslot_clock,
    sort_timeslot_docs,
)


def test_normalize_timeslot_clock_rejects_invalid_minute():
    with pytest.raises(ValueError, match="minute must be one of 00, 15, 30, 45"):
        normalize_timeslot_clock("MONDAY", "09", "10", "AM")


def test_normalize_timeslot_category_defaults_to_category_one():
    assert normalize_timeslot_category(None) == "Category 1"


def test_sort_timeslot_docs_orders_by_day_then_time():
    docs = [
        {"day_of_week": "WEDNESDAY", "hour": "12", "minute": "15", "ampm": "PM"},
        {"day_of_week": "MONDAY", "hour": "12", "minute": "00", "ampm": "PM"},
        {"day_of_week": "MONDAY", "hour": "09", "minute": "15", "ampm": "AM"},
    ]

    sorted_docs = sort_timeslot_docs(docs)

    assert [doc["day_of_week"] for doc in sorted_docs] == ["MONDAY", "MONDAY", "WEDNESDAY"]
    assert [(doc["hour"], doc["minute"], doc["ampm"]) for doc in sorted_docs[:2]] == [
        ("09", "15", "AM"),
        ("12", "00", "PM"),
    ]


def test_find_next_available_timeslot_skips_taken_slot():
    now = datetime(2026, 5, 24, 8, 0, tzinfo=timezone.utc)  # Sunday
    slots = [
        {"day_of_week": "SUNDAY", "hour": "09", "minute": "00", "ampm": "AM"},
        {"day_of_week": "SUNDAY", "hour": "10", "minute": "00", "ampm": "AM"},
    ]
    occupied = {datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc).isoformat()}

    result = find_next_available_timeslot(slots, occupied, now=now)

    assert result == datetime(2026, 5, 24, 10, 0, tzinfo=timezone.utc)
