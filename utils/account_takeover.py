"""
Phase 6.5 — Account takeover detection.
Detects impossible travel (login from two geographically distant locations
in a timeframe that would require faster-than-possible travel).
"""
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Max plausible travel speed in km/h (commercial flight + transit)
_MAX_SPEED_KMH = 900.0
# Minimum distance (km) to trigger impossible travel alert
_MIN_DISTANCE_KM = 500.0


class GeoPoint(NamedTuple):
    lat: float
    lon: float


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance between two lat/lon points in kilometres."""
    R = 6371.0  # Earth's mean radius in km
    phi1 = math.radians(a.lat)
    phi2 = math.radians(b.lat)
    d_phi = math.radians(b.lat - a.lat)
    d_lam = math.radians(b.lon - a.lon)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(h))


def is_impossible_travel(
    prev_lat: float,
    prev_lon: float,
    prev_time: datetime,
    curr_lat: float,
    curr_lon: float,
    curr_time: datetime,
) -> bool:
    """
    Returns True if the two login events are geographically impossible given
    the elapsed time. Uses haversine distance + max plausible speed.
    """
    dist_km = haversine_km(GeoPoint(prev_lat, prev_lon), GeoPoint(curr_lat, curr_lon))
    if dist_km < _MIN_DISTANCE_KM:
        return False  # Too close to flag as impossible

    elapsed_hours = (curr_time - prev_time).total_seconds() / 3600.0
    if elapsed_hours <= 0:
        return True  # Same-second login from distant location — impossible

    effective_speed = dist_km / elapsed_hours
    return effective_speed > _MAX_SPEED_KMH


async def check_and_flag_takeover(
    db,
    user_id: str,
    curr_lat: float | None,
    curr_lon: float | None,
    curr_ip: str,
) -> bool:
    """
    Look up the user's last login event and check for impossible travel.
    If detected, logs a warning and stores a security_events document.
    Returns True if impossible travel was detected.
    """
    if curr_lat is None or curr_lon is None:
        return False  # No geo data — skip check

    now = datetime.now(timezone.utc)
    lookback = now - timedelta(hours=24)

    last_login = await db.login_events.find_one(
        {"user_id": user_id, "created_at": {"$gte": lookback}},
        sort=[("created_at", -1)],
    )

    if not last_login or not last_login.get("lat") or not last_login.get("lon"):
        # No prior geo event — store current and return
        await db.login_events.insert_one({
            "user_id": user_id,
            "ip": curr_ip,
            "lat": curr_lat,
            "lon": curr_lon,
            "created_at": now,
        })
        return False

    flagged = is_impossible_travel(
        prev_lat=float(last_login["lat"]),
        prev_lon=float(last_login["lon"]),
        prev_time=last_login["created_at"],
        curr_lat=curr_lat,
        curr_lon=curr_lon,
        curr_time=now,
    )

    if flagged:
        logger.warning(
            "Impossible travel detected for user=%s from ip=%s", user_id, curr_ip
        )
        await db.security_events.insert_one({
            "type": "impossible_travel",
            "user_id": user_id,
            "prev_ip": last_login.get("ip"),
            "curr_ip": curr_ip,
            "prev_location": {"lat": last_login["lat"], "lon": last_login["lon"]},
            "curr_location": {"lat": curr_lat, "lon": curr_lon},
            "detected_at": now,
        })

    # Always store current login event
    await db.login_events.insert_one({
        "user_id": user_id,
        "ip": curr_ip,
        "lat": curr_lat,
        "lon": curr_lon,
        "created_at": now,
    })

    return flagged
