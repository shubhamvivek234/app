"""
Instagram Business Login (Standalone)
Uses Instagram API with Instagram Login — does NOT require a Facebook Page.
Official docs: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login
"""
import httpx
import os
import logging
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
import urllib.parse


class InstagramAuth:
    """Instagram Business Login standalone (no Facebook Page required)"""

    _API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v21.0")
    # Meta "Instagram API with Instagram login" uses this endpoint (matches Meta UI embed URL).
    OAUTH_URL = "https://www.instagram.com/oauth/authorize"
    TOKEN_URL = "https://api.instagram.com/oauth/access_token"
    GRAPH_URL = f"https://graph.instagram.com/{_API_VERSION}"

    def __init__(self):
        self.app_id = os.environ.get("INSTAGRAM_APP_ID") or os.environ.get("FACEBOOK_APP_ID")
        self.app_secret = os.environ.get("INSTAGRAM_APP_SECRET") or os.environ.get("FACEBOOK_APP_SECRET")
        
        raw_uri = os.environ.get("INSTAGRAM_REDIRECT_URI") or os.environ.get("FACEBOOK_REDIRECT_URI", "").replace(
            "/oauth/facebook/callback", "/oauth/instagram/callback"
        )
        
        # Postiz Bypass: Wrap local HTTP URLs in the redirectmeto HTTPS proxy for Meta API
        if raw_uri.startswith('http://'):
            self.redirect_uri = f"https://redirectmeto.com/{raw_uri}"
        else:
            self.redirect_uri = raw_uri

    @staticmethod
    def _normalize_daily_insight_series(values: list[dict] | None) -> list[dict]:
        normalized = []
        for point in values or []:
            value = point.get("value")
            end_time = point.get("end_time")
            if value is None or not end_time:
                continue
            try:
                count = int(value or 0)
            except (TypeError, ValueError):
                continue
            normalized.append({
                "date": str(end_time)[:10],
                "count": count,
            })
        normalized.sort(key=lambda point: point["date"])
        return normalized

    @staticmethod
    def _response_error(response_json: dict | None) -> str | None:
        error = (response_json or {}).get("error") or {}
        if isinstance(error, dict):
            return error.get("message") or error.get("error_user_msg") or error.get("type")
        if error:
            return str(error)
        return None

    @staticmethod
    def _extract_breakdowns(metric_row: dict) -> list[dict]:
        breakdown_sets = []
        total_value = metric_row.get("total_value")
        if isinstance(total_value, dict):
            breakdowns = total_value.get("breakdowns")
            if isinstance(breakdowns, list):
                breakdown_sets.extend(breakdowns)

        direct_value = metric_row.get("value")
        if isinstance(direct_value, dict):
            breakdowns = direct_value.get("breakdowns")
            if isinstance(breakdowns, list):
                breakdown_sets.extend(breakdowns)

        for point in metric_row.get("values", []) or []:
            point_value = point.get("value")
            if isinstance(point_value, dict):
                breakdowns = point_value.get("breakdowns")
                if isinstance(breakdowns, list):
                    breakdown_sets.extend(breakdowns)

        return breakdown_sets

    @staticmethod
    def _extract_signed_follower_count(raw_value) -> int | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, (int, float)):
            return int(raw_value)
        if not isinstance(raw_value, dict):
            return None

        normalized = {str(key).lower(): value for key, value in raw_value.items()}
        follows = 0
        unfollows = 0
        has_follows = False
        has_unfollows = False

        for key in (
            "follows",
            "followed",
            "followers",
            "new_followers",
            "accounts_followed",
            "followers_count",
        ):
            if key in normalized and normalized[key] is not None:
                try:
                    follows = int(normalized[key])
                    has_follows = True
                    break
                except (TypeError, ValueError):
                    pass

        for key in (
            "unfollows",
            "unfollowed",
            "nonfollowers",
            "unfollowers",
            "accounts_unfollowed",
            "followers_lost",
        ):
            if key in normalized and normalized[key] is not None:
                try:
                    unfollows = int(normalized[key])
                    has_unfollows = True
                    break
                except (TypeError, ValueError):
                    pass

        if has_follows or has_unfollows:
            return follows - unfollows

        for key in ("net", "net_followers", "total", "value"):
            if key in normalized and normalized[key] is not None:
                try:
                    return int(normalized[key])
                except (TypeError, ValueError):
                    pass

        return None

    def get_auth_url(self, state: str) -> str:
        """Generate Instagram Business Login authorization URL"""
        if not self.app_id or not self.redirect_uri:
            raise HTTPException(status_code=500, detail="Instagram credentials not configured")

        # Allow scope override without code changes (useful during Meta app review).
        scope = os.environ.get(
            "INSTAGRAM_OAUTH_SCOPE",
            "instagram_business_basic,instagram_business_content_publish,instagram_business_manage_comments,instagram_business_manage_insights,instagram_business_manage_messages",
        )

        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
            "response_type": "code",
            "state": state,
        }

        # Helps when users previously denied scopes and need to re-grant.
        if os.environ.get("INSTAGRAM_OAUTH_FORCE_REAUTH", "true").lower() in {"1", "true", "yes"}:
            params["force_reauth"] = "true"
        
        auth_url = f"{self.OAUTH_URL}?{urllib.parse.urlencode(params)}"
        logging.info(f"[Instagram] Generated Auth URL: {auth_url}")
        return auth_url

    async def exchange_code_for_token(self, code: str) -> dict:
        """Exchange authorization code for short-lived access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": self.app_id,
                    "client_secret": self.app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                    "code": code,
                },
            )

            logging.info(f"[Instagram] Token exchange status: {response.status_code}")
            logging.info(f"[Instagram] Token exchange response: {response.text[:500]}")

            if response.status_code != 200:
                logging.error(f"[Instagram] Token exchange failed: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to exchange Instagram code: {response.text}")

            return response.json()

    async def get_long_lived_token(self, short_lived_token: str) -> dict:
        """Exchange short-lived token for long-lived token (60 days)"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": self.app_secret,
                    "access_token": short_lived_token,
                },
            )

            logging.info(f"[Instagram] Long-lived token status: {response.status_code}")
            if response.status_code != 200:
                logging.warning(f"[Instagram] Long-lived token failed: {response.text}, using short-lived")
                return {"access_token": short_lived_token}

            return response.json()

    async def get_user_profile(self, access_token: str) -> dict:
        """Get Instagram user profile using the new Business Login API"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/me",
                params={
                    "fields": "id,name,username,profile_picture_url,followers_count,media_count",
                    "access_token": access_token,
                },
            )

            logging.info(f"[Instagram] /me status: {response.status_code}")
            logging.info(f"[Instagram] /me response: {response.text[:500]}")

            if response.status_code != 200:
                logging.error(f"[Instagram] /me failed: {response.text}")
                raise HTTPException(status_code=400, detail=f"Failed to fetch Instagram profile: {response.text}")

            return response.json()

    async def create_video_container(self, access_token: str, ig_user_id: str, video_url: str, caption: str = "") -> str:
        """
        Step 1 only: Create Instagram REELS container. Returns container_id.
        Does NOT poll or publish — non-blocking.
        check_container_status() and publish_container() are called separately.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.GRAPH_URL}/{ig_user_id}/media",
                params={
                    "access_token": access_token,
                    "caption": caption,
                    "media_type": "REELS",
                    "video_url": video_url,
                }
            )
            if response.status_code != 200:
                raise Exception(f"Failed to create IG video container: {response.text}")
            container_id = response.json().get("id")
            if not container_id:
                raise Exception(f"No container_id returned: {response.text}")
            return container_id

    async def check_container_status(self, access_token: str, container_id: str) -> str:
        """
        Check Instagram media container processing status.
        Returns status_code: "FINISHED", "IN_PROGRESS", "ERROR", or "EXPIRED".
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/{container_id}",
                params={"fields": "status_code", "access_token": access_token}
            )
            if response.status_code != 200:
                return "ERROR"
            return response.json().get("status_code", "IN_PROGRESS")

    async def publish_container(self, access_token: str, ig_user_id: str, container_id: str) -> str:
        """
        Step 3 only: Publish a FINISHED container. Returns media post ID.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.GRAPH_URL}/{ig_user_id}/media_publish",
                params={"access_token": access_token, "creation_id": container_id}
            )
            if response.status_code != 200:
                raise Exception(f"Failed to publish IG container: {response.text}")
            return response.json().get("id", "")

    async def publish_to_instagram(self, access_token: str, ig_user_id: str, media_url: str, caption: str = "", media_type: str = "IMAGE") -> str:
        """
        Publish media to Instagram using the Standalone API
        1. Create Media Container
        2. Check Status (if video)
        3. Publish Media Container
        """
        async with httpx.AsyncClient() as client:
            # 1. Create Media Container
            container_url = f"{self.GRAPH_URL}/{ig_user_id}/media"
            params = {
                "access_token": access_token,
                "caption": caption
            }
            
            if media_type == "VIDEO":
                params["media_type"] = "REELS" 
                params["video_url"] = media_url
            else:
                params["image_url"] = media_url
            
            response = await client.post(container_url, params=params)
            
            if response.status_code != 200:
                error_msg = response.text
                logging.error(f"[Standalone IG] Container Create Error: {error_msg}")
                raise Exception(f"Failed to create standalone IG media container: {error_msg}")
                
            container_id = response.json().get("id")
            
            # 2. If VIDEO, wait for status to be FINISHED
            if media_type == "VIDEO":
                import asyncio
                status_url = f"{self.GRAPH_URL}/{container_id}"
                status_params = {
                    "fields": "status_code",
                    "access_token": access_token
                }
                
                max_retries = 30 # 30 * 5s = 2.5 minutes timeout
                for _ in range(max_retries):
                    status_response = await client.get(status_url, params=status_params)
                    if status_response.status_code == 200:
                        status_code = status_response.json().get("status_code")
                        if status_code == "FINISHED":
                            break
                        elif status_code == "ERROR":
                            raise Exception("Standalone IG video processing failed")
                    
                    await asyncio.sleep(5)
            
            # 3. Publish Container
            publish_url = f"{self.GRAPH_URL}/{ig_user_id}/media_publish"
            publish_params = {
                "access_token": access_token,
                "creation_id": container_id
            }
            
            publish_response = await client.post(publish_url, params=publish_params)
            
            if publish_response.status_code != 200:
                error_msg = publish_response.text
                logging.error(f"[Standalone IG] Publish Error: {error_msg}")
                raise Exception(f"Failed to publish to standalone IG: {error_msg}")
                
            return publish_response.json().get("id")

    async def fetch_feed(self, access_token: str, user_id: str, limit: int = 25) -> list:
        """Fetch recent media from Instagram"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/{user_id}/media",
                params={
                    "fields": "id,caption,media_type,media_url,thumbnail_url,timestamp,like_count,comments_count,permalink",
                    "limit": limit,
                    "access_token": access_token,
                },
            )
            if response.status_code != 200:
                logging.warning(f"[Instagram] Feed fetch failed: {response.text}")
                return []
            posts = response.json().get("data", [])
            result = []
            for post in posts:
                media_type = post.get("media_type", "IMAGE")
                if media_type in ("VIDEO", "REELS"):
                    display_url = post.get("thumbnail_url") or post.get("media_url")
                    video_url = post.get("media_url")
                else:
                    display_url = post.get("media_url") or post.get("thumbnail_url")
                    video_url = None
                result.append({
                    "id": post.get("id"),
                    "content": post.get("caption", ""),
                    "media_url": display_url,
                    "video_url": video_url,
                    "media_type": media_type,
                    "timestamp": post.get("timestamp"),
                    "likes": post.get("like_count", 0),
                    "comments_count": post.get("comments_count", 0),
                    "permalink": post.get("permalink"),
                    "platform": "instagram",
                })
            return result

    async def fetch_engagement(self, access_token: str, user_id: str, days: int | None = None) -> dict:
        """Fetch Instagram account engagement metrics"""
        async with httpx.AsyncClient() as client:
            # Get user profile stats
            response = await client.get(
                f"{self.GRAPH_URL}/{user_id}",
                params={
                    "fields": "id,username,followers_count,follows_count,media_count",
                    "access_token": access_token,
                },
            )
            if response.status_code != 200:
                return {}
            profile = response.json()

            # Get insights
            insights = {}
            insight_series = {
                "impressions": [],
                "reach": [],
                "profile_views": [],
            }
            followers_growth = None
            try:
                range_days = max(int(days or 30), 1)
                until_dt = datetime.now(timezone.utc)
                since_dt = until_dt - timedelta(days=range_days)
                for metric_name in ("impressions", "reach", "profile_views"):
                    metric_resp = await client.get(
                        f"{self.GRAPH_URL}/{user_id}/insights",
                        params={
                            "metric": metric_name,
                            "period": "day",
                            "since": since_dt.date().isoformat(),
                            "until": until_dt.date().isoformat(),
                            "access_token": access_token,
                        },
                    )
                    if metric_resp.status_code != 200:
                        logging.warning(f"[Instagram] Insight {metric_name} fetch failed: {metric_resp.text}")
                        continue

                    for item in metric_resp.json().get("data", []):
                        name = item.get("name")
                        if not name:
                            continue
                        normalized_series = self._normalize_daily_insight_series(item.get("values", []))
                        if normalized_series:
                            insight_series[name] = normalized_series
                        if item.get("total_value", {}).get("value") is not None:
                            insights[name] = int(item.get("total_value", {}).get("value", 0) or 0)
                            continue
                        if normalized_series:
                            insights[name] = sum(point["count"] for point in normalized_series)
                growth_resp = await client.get(
                    f"{self.GRAPH_URL}/{user_id}/insights",
                    params={
                        "metric": "follower_count",
                        "period": "day",
                        "since": since_dt.date().isoformat(),
                        "until": until_dt.date().isoformat(),
                        "access_token": access_token,
                    },
                )
                if growth_resp.status_code == 200:
                    values = [
                        int(point.get("value", 0))
                        for item in growth_resp.json().get("data", [])
                        for point in item.get("values", [])
                        if point.get("value") is not None
                    ]
                    if len(values) >= 2:
                        followers_growth = values[-1] - values[0]
            except Exception as e:
                logging.warning(f"[Instagram] Insights fetch failed: {e}")

            return {
                "followers": profile.get("followers_count", 0),
                "following": profile.get("follows_count", 0),
                "posts_count": profile.get("media_count", 0),
                "followers_growth": followers_growth,
                "impressions": insights.get("impressions", 0),
                "reach": insights.get("reach", 0),
                "profile_views": insights.get("profile_views", 0),
                "impressions_series": insight_series.get("impressions", []),
                "reach_series": insight_series.get("reach", []),
                "profile_views_series": insight_series.get("profile_views", []),
                "platform": "instagram",
            }

    async def fetch_demographics(
        self,
        access_token: str,
        user_id: str,
        metric: str = "follower_demographics",
        timeframe: str | None = None,
    ) -> dict:
        """Fetch Instagram demographic breakdowns for a selected audience metric."""
        async with httpx.AsyncClient() as client:
            result = {
                "age": [],
                "gender": [],
                "cities": [],
                "countries": [],
                "supported": False,
                "metric": metric,
                "timeframe": timeframe,
                "attempted_requests": [],
            }
            dimension_to_key = {
                "age": "age",
                "gender": "gender",
                "city": "cities",
                "country": "countries",
            }
            request_variants = []
            base_variants = [
                {"period": "lifetime", "metric_type": "total_value"},
                {"metric_type": "total_value"},
                {"period": "lifetime"},
                {},
            ]
            if timeframe:
                request_variants.extend(
                    [{**variant, "timeframe": timeframe} for variant in base_variants]
                )
            request_variants.extend(base_variants)

            deduped_variants = []
            seen_variants = set()
            for variant in request_variants:
                marker = tuple(sorted(variant.items()))
                if marker in seen_variants:
                    continue
                seen_variants.add(marker)
                deduped_variants.append(variant)
            request_variants = deduped_variants

            def _append_dimension_values(target_result: dict, breakdown: str, values: list[dict]) -> bool:
                if not values:
                    return False
                target_key = dimension_to_key[breakdown]
                if breakdown == "age":
                    target_result[target_key].extend(
                        {"range": item["label"], "count": item["count"]}
                        for item in values
                    )
                elif breakdown == "gender":
                    target_result[target_key].extend(
                        {"label": item["label"], "count": item["count"]}
                        for item in values
                    )
                elif breakdown == "city":
                    target_result[target_key].extend(
                        {"name": item["label"], "count": item["count"]}
                        for item in sorted(values, key=lambda item: item["count"], reverse=True)[:10]
                    )
                elif breakdown == "country":
                    target_result[target_key].extend(
                        {"name": item["label"], "count": item["count"]}
                        for item in sorted(values, key=lambda item: item["count"], reverse=True)[:10]
                    )
                return True

            for breakdown in ("age", "gender", "city", "country"):
                for extra_params in request_variants:
                    params = {
                        "metric": metric,
                        "breakdown": breakdown,
                        "access_token": access_token,
                        **extra_params,
                    }
                    safe_params = {key: value for key, value in params.items() if key != "access_token"}
                    result["attempted_requests"].append({"breakdown": breakdown, **safe_params})

                    response = await client.get(
                        f"{self.GRAPH_URL}/{user_id}/insights",
                        params=params,
                    )
                    response_json = response.json() if response.text else {}
                    response_error = self._response_error(response_json)
                    if response.status_code != 200:
                        logging.warning(
                            "[Instagram] Demographics fetch failed for %s/%s with params %s: %s",
                            metric,
                            breakdown,
                            safe_params,
                            response.text,
                        )
                        continue
                    if response_error:
                        logging.warning(
                            "[Instagram] Demographics API returned error for %s/%s with params %s: %s",
                            metric,
                            breakdown,
                            safe_params,
                            response_error,
                        )
                        continue

                    data = response_json.get("data", [])
                    matched_values = []
                    for metric_row in data:
                        breakdowns = self._extract_breakdowns(metric_row)
                        for breakdown_row in breakdowns:
                            dimension_keys = breakdown_row.get("dimension_keys", [])
                            if breakdown not in dimension_keys:
                                continue
                            dimension_index = dimension_keys.index(breakdown)
                            for row in breakdown_row.get("results", []):
                                dimension_values = row.get("dimension_values", [])
                                if len(dimension_values) <= dimension_index:
                                    continue
                                matched_values.append(
                                    {
                                        "label": dimension_values[dimension_index],
                                        "count": row.get("value", 0),
                                    }
                                )

                    if _append_dimension_values(result, breakdown, matched_values):
                        break

            if not any(result[key] for key in ("age", "gender", "cities", "countries")) and metric == "follower_demographics":
                legacy_response = await client.get(
                    f"{self.GRAPH_URL}/{user_id}/insights",
                    params={
                        "metric": "follower_demographics",
                        "period": "lifetime",
                        "metric_type": "total_value",
                        "access_token": access_token,
                    },
                )
                legacy_json = legacy_response.json() if legacy_response.text else {}
                legacy_error = self._response_error(legacy_json)
                if legacy_response.status_code == 200 and not legacy_error:
                    data = legacy_json.get("data", [])
                    for metric_row in data:
                        breakdowns = self._extract_breakdowns(metric_row)
                        for breakdown_row in breakdowns:
                            dimension_keys = breakdown_row.get("dimension_keys", [])
                            if not dimension_keys:
                                continue
                            breakdown = dimension_keys[0]
                            if breakdown not in dimension_to_key:
                                continue
                            matched_values = []
                            for row in breakdown_row.get("results", []):
                                dimension_values = row.get("dimension_values", [])
                                if not dimension_values:
                                    continue
                                matched_values.append(
                                    {
                                        "label": dimension_values[0],
                                        "count": row.get("value", 0),
                                    }
                                )
                            _append_dimension_values(result, breakdown, matched_values)
                else:
                    logging.warning(
                        "[Instagram] Legacy follower demographics fetch failed: %s",
                        legacy_error or legacy_response.text,
                    )

            result["supported"] = any(result[key] for key in ("age", "gender", "cities", "countries"))
            if not result["supported"]:
                result["error"] = f"Instagram did not return usable {metric} breakdowns for this account."
            return result

    async def fetch_follower_growth(self, access_token: str, user_id: str, days: int | None = None) -> dict:
        """Fetch daily net follower movement for the selected period."""
        async with httpx.AsyncClient() as client:
            range_days = max(int(days or 30), 1)
            until_dt = datetime.now(timezone.utc)
            since_dt = until_dt - timedelta(days=range_days)
            attempt_errors = []

            async def _request_growth(metric_name: str) -> tuple[list[dict], str | None]:
                response = await client.get(
                    f"{self.GRAPH_URL}/{user_id}/insights",
                    params={
                        "metric": metric_name,
                        "period": "day",
                        "since": since_dt.date().isoformat(),
                        "until": until_dt.date().isoformat(),
                        "access_token": access_token,
                    },
                )
                response_json = response.json() if response.text else {}
                response_error = self._response_error(response_json)
                if response.status_code != 200 or response_error:
                    return [], response_error or response.text or f"Could not fetch {metric_name}"

                series = []
                for item in response_json.get("data", []):
                    for point in item.get("values", []):
                        signed_value = self._extract_signed_follower_count(point.get("value"))
                        end_time = point.get("end_time")
                        if signed_value is None or not end_time:
                            continue
                        series.append({
                            "date": end_time[:10],
                            "count": signed_value,
                        })
                series.sort(key=lambda point: point["date"])
                if not series:
                    return [], f"No usable {metric_name} data returned"
                return series, None

            series, primary_error = await _request_growth("follower_count")
            if series:
                growth = sum(int(point["count"]) for point in series)
                return {
                    "supported": True,
                    "source": "follower_count",
                    "series": series,
                    "growth_series": series,
                    "growth": growth,
                    "error": None,
                }
            if primary_error:
                attempt_errors.append(f"follower_count: {primary_error}")

            fallback_series, fallback_error = await _request_growth("follows_and_unfollows")
            if fallback_series:
                growth = sum(int(point["count"]) for point in fallback_series)
                return {
                    "supported": True,
                    "source": "follows_and_unfollows",
                    "series": fallback_series,
                    "growth_series": fallback_series,
                    "growth": growth,
                    "error": None,
                }
            if fallback_error:
                attempt_errors.append(f"follows_and_unfollows: {fallback_error}")

            error_message = (
                "; ".join(attempt_errors)
                if attempt_errors
                else "Instagram did not return follower growth insights for this account."
            )
            logging.warning("[Instagram] Follower growth unavailable: %s", error_message)
            return {
                "supported": False,
                "source": None,
                "series": [],
                "growth_series": [],
                "growth": 0,
                "error": error_message,
            }

    async def fetch_comments(self, access_token: str, media_id: str, limit: int = 50) -> list:
        """Fetch comments on a media post"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/{media_id}/comments",
                params={
                    "fields": "id,text,username,timestamp,like_count",
                    "limit": limit,
                    "access_token": access_token,
                },
            )
            if response.status_code != 200:
                logging.warning(f"[Instagram] Comments fetch failed: {response.text}")
                return []
            comments = []
            for c in response.json().get("data", []):
                comments.append({
                    "id": c.get("id"),
                    "author_name": c.get("username", "Unknown"),
                    "author_avatar": None,
                    "content": c.get("text", ""),
                    "timestamp": c.get("timestamp"),
                    "likes": c.get("like_count", 0),
                    "can_reply": True,
                    "platform": "instagram",
                })
            return comments

    async def reply_to_comment(self, access_token: str, comment_id: str, text: str) -> dict:
        """Reply to a comment on Instagram"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.GRAPH_URL}/{comment_id}/replies",
                params={
                    "message": text,
                    "access_token": access_token,
                },
            )
            if response.status_code != 200:
                logging.error(f"[Instagram] Reply failed: {response.text}")
                raise Exception(f"Failed to reply: {response.text}")
            return response.json()

    async def fetch_conversations(self, access_token: str, user_id: str, limit: int = 20) -> list:
        """Fetch Instagram DM conversations"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.GRAPH_URL}/{user_id}/conversations",
                params={
                    "fields": "id,participants{id,name,username,profile_picture_url},messages{id,message,from{id,name,username,profile_picture_url},created_time}",
                    "limit": limit,
                    "access_token": access_token,
                },
            )
            if response.status_code != 200:
                logging.warning(f"[Instagram] DM fetch failed: {response.text}")
                return []
            conversations = []
            for conv in response.json().get("data", []):
                participants = [
                    {
                        "id": participant.get("id"),
                        "name": participant.get("name"),
                        "username": participant.get("username"),
                        "avatar": participant.get("profile_picture_url"),
                    }
                    for participant in conv.get("participants", {}).get("data", [])
                ]
                messages = []
                for message in conv.get("messages", {}).get("data", []):
                    sender = message.get("from", {}) or {}
                    messages.append({
                        "id": message.get("id"),
                        "message": message.get("message", ""),
                        "created_time": message.get("created_time"),
                        "from": {
                            "id": sender.get("id"),
                            "name": sender.get("name"),
                            "username": sender.get("username"),
                            "avatar": sender.get("profile_picture_url"),
                        },
                    })
                latest = messages[0] if messages else {}
                latest_sender = latest.get("from", {}) or {}
                conversations.append({
                    "id": conv.get("id"),
                    "participants": participants,
                    "messages": messages,
                    "last_message": latest.get("message", ""),
                    "last_message_time": latest.get("created_time"),
                    "last_message_id": latest.get("id"),
                    "last_message_sender_id": latest_sender.get("id"),
                    "last_message_sender_name": latest_sender.get("name") or latest_sender.get("username") or "Unknown",
                    "platform": "instagram",
                })
            return conversations

    async def send_message(self, access_token: str, recipient_id: str, text: str) -> dict:
        """Send a DM on Instagram"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.GRAPH_URL}/me/messages",
                params={"access_token": access_token},
                json={"recipient": {"id": recipient_id}, "message": {"text": text}},
            )
            if response.status_code != 200:
                logging.error(f"[Instagram] DM send failed: {response.text}")
                raise Exception(f"Failed to send message: {response.text}")
            return response.json()
