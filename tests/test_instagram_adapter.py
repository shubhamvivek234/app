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
