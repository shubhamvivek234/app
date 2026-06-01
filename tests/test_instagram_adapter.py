import pytest

from backend.app.social.instagram import InstagramAuth


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _FakeAsyncClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        return self._response


class _QueuedAsyncClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        self.calls.append(kwargs.get("params", {}))
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_fetch_engagement_returns_totals_and_daily_series(monkeypatch):
    client = _QueuedAsyncClient(
        [
            _FakeResponse(
                200,
                {
                    "id": "ig-user",
                    "username": "creator",
                    "followers_count": 120,
                    "follows_count": 12,
                    "media_count": 8,
                },
            ),
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "name": "impressions",
                            "values": [
                                {"value": 10, "end_time": "2026-05-20T07:00:00+0000"},
                                {"value": 15, "end_time": "2026-05-21T07:00:00+0000"},
                            ],
                        }
                    ]
                },
            ),
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "name": "reach",
                            "values": [
                                {"value": 7, "end_time": "2026-05-20T07:00:00+0000"},
                                {"value": 11, "end_time": "2026-05-21T07:00:00+0000"},
                            ],
                        }
                    ]
                },
            ),
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "name": "profile_views",
                            "values": [
                                {"value": 2, "end_time": "2026-05-20T07:00:00+0000"},
                                {"value": 4, "end_time": "2026-05-21T07:00:00+0000"},
                            ],
                        }
                    ]
                },
            ),
            _FakeResponse(200, {"data": []}),
        ]
    )

    monkeypatch.setattr(
        "backend.app.social.instagram.httpx.AsyncClient",
        lambda: client,
    )

    auth = InstagramAuth()
    result = await auth.fetch_engagement("token", "ig-user", days=30)

    assert result["followers"] == 120
    assert result["following"] == 12
    assert result["posts_count"] == 8
    assert result["impressions"] == 25
    assert result["reach"] == 18
    assert result["profile_views"] == 6
    assert result["impressions_series"] == [
        {"date": "2026-05-20", "count": 10},
        {"date": "2026-05-21", "count": 15},
    ]
    assert result["reach_series"] == [
        {"date": "2026-05-20", "count": 7},
        {"date": "2026-05-21", "count": 11},
    ]
    assert result["profile_views_series"] == [
        {"date": "2026-05-20", "count": 2},
        {"date": "2026-05-21", "count": 4},
    ]


@pytest.mark.asyncio
async def test_fetch_follower_growth_preserves_daily_net_series(monkeypatch):
    response = _FakeResponse(
        200,
        {
            "data": [
                {
                    "name": "follower_count",
                    "values": [
                        {"value": -2, "end_time": "2026-05-20T07:00:00+0000"},
                        {"value": 3, "end_time": "2026-05-21T07:00:00+0000"},
                        {"value": -1, "end_time": "2026-05-22T07:00:00+0000"},
                    ],
                }
            ]
        },
    )

    monkeypatch.setattr(
        "backend.app.social.instagram.httpx.AsyncClient",
        lambda: _FakeAsyncClient(response),
    )

    auth = InstagramAuth()
    result = await auth.fetch_follower_growth("token", "ig-user", days=30)

    assert result["supported"] is True
    assert result["series"] == [
        {"date": "2026-05-20", "count": -2},
        {"date": "2026-05-21", "count": 3},
        {"date": "2026-05-22", "count": -1},
    ]
    assert result["growth_series"] == result["series"]
    assert result["growth"] == 0


@pytest.mark.asyncio
async def test_fetch_demographics_uses_engaged_metric_with_per_breakdown_requests(monkeypatch):
    client = _QueuedAsyncClient(
        [
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "total_value": {
                                "breakdowns": [
                                    {
                                        "dimension_keys": ["timeframe", "age"],
                                        "results": [
                                            {"dimension_values": ["THIS_MONTH", "18-24"], "value": 12},
                                        ],
                                    }
                                ]
                            }
                        }
                    ]
                },
            ),
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "total_value": {
                                "breakdowns": [
                                    {
                                        "dimension_keys": ["timeframe", "gender"],
                                        "results": [
                                            {"dimension_values": ["THIS_MONTH", "female"], "value": 9},
                                        ],
                                    }
                                ]
                            }
                        }
                    ]
                },
            ),
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "total_value": {
                                "breakdowns": [
                                    {
                                        "dimension_keys": ["timeframe", "city"],
                                        "results": [
                                            {"dimension_values": ["THIS_MONTH", "Mumbai"], "value": 7},
                                        ],
                                    }
                                ]
                            }
                        }
                    ]
                },
            ),
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "total_value": {
                                "breakdowns": [
                                    {
                                        "dimension_keys": ["timeframe", "country"],
                                        "results": [
                                            {"dimension_values": ["THIS_MONTH", "IN"], "value": 14},
                                        ],
                                    }
                                ]
                            }
                        }
                    ]
                },
            ),
        ]
    )

    monkeypatch.setattr(
        "backend.app.social.instagram.httpx.AsyncClient",
        lambda: client,
    )

    auth = InstagramAuth()
    result = await auth.fetch_demographics(
        "token",
        "ig-user",
        metric="engaged_audience_demographics",
        timeframe="this_month",
    )

    assert result["supported"] is True
    assert result["metric"] == "engaged_audience_demographics"
    assert result["timeframe"] == "this_month"
    assert result["age"] == [{"range": "18-24", "count": 12}]
    assert result["gender"] == [{"label": "female", "count": 9}]
    assert result["cities"] == [{"name": "Mumbai", "count": 7}]
    assert result["countries"] == [{"name": "IN", "count": 14}]
    assert [call["breakdown"] for call in client.calls] == ["age", "gender", "city", "country"]
    assert all(call["metric"] == "engaged_audience_demographics" for call in client.calls)
    assert all(call["timeframe"] == "this_month" for call in client.calls)
    assert all(call["period"] == "lifetime" for call in client.calls)


@pytest.mark.asyncio
async def test_fetch_demographics_falls_back_to_legacy_follower_response(monkeypatch):
    client = _QueuedAsyncClient(
        ([_FakeResponse(200, {"data": []})] * 8)
        + [
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "total_value": {
                                "breakdowns": [
                                    {
                                        "dimension_keys": ["age"],
                                        "results": [
                                            {"dimension_values": ["25-34"], "value": 5},
                                        ],
                                    },
                                    {
                                        "dimension_keys": ["country"],
                                        "results": [
                                            {"dimension_values": ["US"], "value": 8},
                                        ],
                                    },
                                ]
                            }
                        }
                    ]
                },
            ),
        ]
    )

    monkeypatch.setattr(
        "backend.app.social.instagram.httpx.AsyncClient",
        lambda: client,
    )

    auth = InstagramAuth()
    result = await auth.fetch_demographics("token", "ig-user")

    assert result["supported"] is True
    assert result["metric"] == "follower_demographics"
    assert result["age"] == [{"range": "25-34", "count": 5}]
    assert result["countries"] == [{"name": "US", "count": 8}]
    assert all(call["period"] == "lifetime" for call in client.calls)


@pytest.mark.asyncio
async def test_fetch_demographics_parses_values_breakdowns_shape(monkeypatch):
    client = _QueuedAsyncClient(
        [
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "values": [
                                {
                                    "value": {
                                        "breakdowns": [
                                            {
                                                "dimension_keys": ["timeframe", "age"],
                                                "results": [
                                                    {"dimension_values": ["THIS_WEEK", "35-44"], "value": 6},
                                                ],
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    ]
                },
            ),
        ] + ([_FakeResponse(200, {"data": []})] * 24)
    )

    monkeypatch.setattr(
        "backend.app.social.instagram.httpx.AsyncClient",
        lambda: client,
    )

    auth = InstagramAuth()
    result = await auth.fetch_demographics(
        "token",
        "ig-user",
        metric="engaged_audience_demographics",
        timeframe="this_week",
    )

    assert result["supported"] is True
    assert result["age"] == [{"range": "35-44", "count": 6}]
    assert client.calls[0]["period"] == "lifetime"


@pytest.mark.asyncio
async def test_fetch_follower_growth_falls_back_to_follows_and_unfollows(monkeypatch):
    client = _QueuedAsyncClient(
        [
            _FakeResponse(200, {"data": []}),
            _FakeResponse(
                200,
                {
                    "data": [
                        {
                            "name": "follows_and_unfollows",
                            "values": [
                                {
                                    "value": {"follows": 5, "unfollows": 2},
                                    "end_time": "2026-05-20T07:00:00+0000",
                                },
                                {
                                    "value": {"follows": 1, "unfollows": 4},
                                    "end_time": "2026-05-21T07:00:00+0000",
                                },
                            ],
                        }
                    ]
                },
            ),
        ]
    )

    monkeypatch.setattr(
        "backend.app.social.instagram.httpx.AsyncClient",
        lambda: client,
    )

    auth = InstagramAuth()
    result = await auth.fetch_follower_growth("token", "ig-user", days=30)

    assert result["supported"] is True
    assert result["source"] == "follows_and_unfollows"
    assert result["growth_series"] == [
        {"date": "2026-05-20", "count": 3},
        {"date": "2026-05-21", "count": -3},
    ]
    assert result["growth"] == 0


@pytest.mark.asyncio
async def test_fetch_follower_growth_returns_explicit_error_when_unavailable(monkeypatch):
    client = _QueuedAsyncClient(
        [
            _FakeResponse(200, {"data": []}),
            _FakeResponse(200, {"data": []}),
        ]
    )

    monkeypatch.setattr(
        "backend.app.social.instagram.httpx.AsyncClient",
        lambda: client,
    )

    auth = InstagramAuth()
    result = await auth.fetch_follower_growth("token", "ig-user", days=30)

    assert result["supported"] is False
    assert result["growth_series"] == []
    assert "follower_count" in result["error"]
    assert "follows_and_unfollows" in result["error"]
    assert result["error_type"] == "empty_response"


@pytest.mark.asyncio
async def test_fetch_demographics_classifies_api_rejections(monkeypatch):
    client = _QueuedAsyncClient(
        [_FakeResponse(400, {"error": {"message": "The parameter period is required"}})] * 16
    )

    monkeypatch.setattr(
        "backend.app.social.instagram.httpx.AsyncClient",
        lambda: client,
    )

    auth = InstagramAuth()
    result = await auth.fetch_demographics(
        "token",
        "ig-user",
        metric="engaged_audience_demographics",
        timeframe="this_month",
    )

    assert result["supported"] is False
    assert result["error_type"] == "api_rejected"
    assert "rejected" in result["error"].lower()
