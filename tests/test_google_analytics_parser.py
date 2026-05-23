from backend.app.social.google import GoogleAuth


def test_normalize_analytics_value_preserves_dimension_strings():
    auth = GoogleAuth()

    assert auth._normalize_analytics_value(
        "SUBSCRIBED",
        {"name": "subscribedStatus", "columnType": "DIMENSION", "dataType": "STRING"},
    ) == "SUBSCRIBED"
    assert auth._normalize_analytics_value(
        "MOBILE",
        {"name": "deviceType", "columnType": "DIMENSION", "dataType": "STRING"},
    ) == "MOBILE"


def test_normalize_analytics_value_converts_metric_numbers():
    auth = GoogleAuth()

    assert auth._normalize_analytics_value(
        "11",
        {"name": "views", "columnType": "METRIC", "dataType": "INTEGER"},
    ) == 11
    assert auth._normalize_analytics_value(
        "0.0727",
        {"name": "estimatedMinutesWatched", "columnType": "METRIC", "dataType": "FLOAT"},
    ) == 0.0727
