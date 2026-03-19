"""
Phase 5.5 (EC10) — DST-safe timezone handling.
Store IANA timezone string on user record, compute UTC fresh at materialisation time.
Never pre-compute UTC for future recurring occurrences.
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def to_utc(local_dt: datetime, iana_tz: str) -> datetime:
    """
    Convert a naive local datetime to UTC using the given IANA timezone.
    Raises ValueError for ambiguous DST times.
    """
    try:
        tz = ZoneInfo(iana_tz)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {iana_tz}") from exc

    if local_dt.tzinfo is not None:
        raise ValueError("local_dt must be a naive (tz-unaware) datetime")

    # fold=0 → first occurrence (pre-DST), fold=1 → second occurrence (post-DST)
    aware_dt = local_dt.replace(tzinfo=tz)

    # Detect ambiguous time (DST fold) by checking if fold matters
    fold1 = local_dt.replace(tzinfo=tz, fold=0)
    fold2 = local_dt.replace(tzinfo=tz, fold=1)
    if fold1.utctimetuple() != fold2.utctimetuple():
        raise ValueError(
            f"Ambiguous DST time: {local_dt} in {iana_tz}. "
            "Please specify whether this is before or after the clock change."
        )

    return aware_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def from_utc(utc_dt: datetime, iana_tz: str) -> datetime:
    """Convert a naive UTC datetime to the given local timezone."""
    try:
        tz = ZoneInfo(iana_tz)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown IANA timezone: {iana_tz}") from exc

    aware_utc = utc_dt.replace(tzinfo=ZoneInfo("UTC"))
    return aware_utc.astimezone(tz).replace(tzinfo=None)


def is_valid_iana_tz(tz_name: str) -> bool:
    try:
        ZoneInfo(tz_name)
        return True
    except ZoneInfoNotFoundError:
        return False
