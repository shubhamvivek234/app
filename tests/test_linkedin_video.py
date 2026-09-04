from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from platform_adapters.linkedin import LinkedInAdapter


def test_build_ugc_body_video():
    adapter = LinkedInAdapter()
    body = adapter._build_ugc_body(
        author_urn="urn:li:person:123",
        text="Check out this video!",
        asset_urn="urn:li:digitalmediaAsset:abc",
        post_type="video",
    )
    share_content = body["specificContent"]["com.linkedin.ugc.ShareContent"]
    assert share_content["shareMediaCategory"] == "VIDEO"
    assert share_content["media"][0]["media"] == "urn:li:digitalmediaAsset:abc"


def test_build_ugc_body_image():
    adapter = LinkedInAdapter()
    body = adapter._build_ugc_body(
        author_urn="urn:li:person:123",
        text="Check out this image!",
        asset_urn="urn:li:digitalmediaAsset:abc",
        post_type="image",
    )
    share_content = body["specificContent"]["com.linkedin.ugc.ShareContent"]
    assert share_content["shareMediaCategory"] == "IMAGE"
    assert share_content["media"][0]["media"] == "urn:li:digitalmediaAsset:abc"


@pytest.mark.asyncio
async def test_linkedin_publish_video():
    adapter = LinkedInAdapter()
    post = {
        "id": "post-xyz",
        "account": {"access_token": "enc-token", "platform_user_id": "usr-1"},
        "media_url": "https://pub-r2.dev/sample.mp4",
        "post_type": "video",
        "content": "Awesome video release",
    }

    with patch("platform_adapters.linkedin.assert_safe_url"):
        with patch("platform_adapters.linkedin.decrypt", return_value="plain-token"):
            with patch.object(adapter, "_register_and_upload_video", AsyncMock(return_value="urn:li:digitalmediaAsset:vid-999")) as mock_reg:
                with patch("httpx.AsyncClient.post") as mock_post:
                    mock_resp = MagicMock()
                    mock_resp.status_code = 201
                    mock_resp.headers = {"x-restli-id": "urn:li:share:123456"}
                    mock_resp.json.return_value = {"id": "urn:li:share:123456"}
                    mock_post.return_value = mock_resp

                    res = await adapter.publish(post)
                    assert res["platform_post_id"] == "urn:li:share:123456"
                    mock_reg.assert_called_once()
