import pytest
from datetime import datetime, timezone
from api.models.post import CreatePostRequest, UpdatePostRequest
from utils.first_comment import post_first_comment


def test_post_create_with_first_comment():
    post = CreatePostRequest(
        content="Testing post caption",
        platforms=["twitter", "linkedin", "discord", "telegram"],
        first_comment="Here is the link: https://unravler.com",
        first_comment_enabled=True,
    )
    assert post.first_comment == "Here is the link: https://unravler.com"
    assert post.first_comment_enabled is True
    assert "discord" in post.platforms
    assert "telegram" in post.platforms


def test_post_update_with_first_comment():
    req = UpdatePostRequest(
        version=1,
        first_comment="Updated comment link",
        first_comment_enabled=True,
    )
    assert req.first_comment == "Updated comment link"
    assert req.first_comment_enabled is True


@pytest.mark.asyncio
async def test_first_comment_empty_skip():
    res = await post_first_comment(
        platform="twitter",
        platform_post_id="12345",
        first_comment_text="",
        account={"access_token": "dummy"},
    )
    assert res["status"] == "skipped"
