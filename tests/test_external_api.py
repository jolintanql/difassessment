from apis.external_api import (
    _normalize_post,
    _normalize_posts_response,
    _normalize_reel,
    _normalize_reels_response,
)


# Verifies that a normal image post is converted into the format the system expects
def test_normalize_post_image():
    item = {
        "media_type": 1,
        "display_url": "http://image.jpg",
        "caption": "test caption",
        "taken_at": 0,
    }

    result = _normalize_post(item, "testuser")

    assert result["content_type"] == "post"
    assert result["owners"] == ["testuser"]
    assert result["caption"] == "test caption"
    assert result["media_content"][0]["media_type"] == "image"
    assert result["media_content"][0]["original_url"] == "http://image.jpg"


# Verifies that a video post is converted correctly
def test_normalize_post_video():
    item = {
        "media_type": 2,
        "video_versions": [{"url": "http://video.mp4"}],
        "display_url": "http://thumb.jpg",
        "caption": "",
        "taken_at": 0,
    }

    result = _normalize_post(item, "testuser")

    assert result["content_type"] == "post"
    assert result["media_content"][0]["media_type"] == "video"
    assert result["media_content"][0]["original_url"] == "http://video.mp4"
    assert result["media_content"][0]["original_thumbnail_url"] == "http://thumb.jpg"


# Verifies that a carousel post keeps all its media items
def test_normalize_post_carousel():
    item = {
        "media_type": 8,
        "caption": {"text": "carousel post"},
        "taken_at": 0,
        "carousel_media": [
            {
                "media_type": 1,
                "display_url": "http://image1.jpg",
            },
            {
                "media_type": 2,
                "video_versions": [{"url": "http://video1.mp4"}],
                "display_url": "http://thumb1.jpg",
            },
        ],
    }

    result = _normalize_post(item, "testuser")

    assert result["content_type"] == "post"
    assert result["caption"] == "carousel post"
    assert len(result["media_content"]) == 2
    assert result["media_content"][0]["media_type"] == "image"
    assert result["media_content"][0]["original_url"] == "http://image1.jpg"
    assert result["media_content"][1]["media_type"] == "video"
    assert result["media_content"][1]["original_url"] == "http://video1.mp4"
    assert result["media_content"][1]["original_thumbnail_url"] == "http://thumb1.jpg"


# Verifies that a valid reel is converted properly
def test_normalize_reel_valid():
    item = {
        "media": {
            "video_versions": [{"url": "http://reel.mp4"}],
            "display_url": "http://thumb.jpg",
            "caption": {"text": "reel caption"},
            "taken_at": 0,
        }
    }

    result = _normalize_reel(item, "testuser")

    assert result is not None
    assert result["content_type"] == "reel"
    assert result["owners"] == ["testuser"]
    assert result["caption"] == "reel caption"
    assert result["media_content"][0]["media_type"] == "video"
    assert result["media_content"][0]["original_url"] == "http://reel.mp4"
    assert result["media_content"][0]["original_thumbnail_url"] == "http://thumb.jpg"


# Verifies that reels with no video are ignored
def test_normalize_reel_no_video_returns_none():
    item = {
        "media": {
            "caption": {"text": "no video"}
        }
    }

    result = _normalize_reel(item, "testuser")

    assert result is None


# Verifies that post results and pagination info are read correctly
def test_normalize_posts_response():
    resp = {
        "data": {
            "items": [
                {
                    "media_type": 1,
                    "display_url": "http://img.jpg",
                    "caption": "post 1",
                    "taken_at": 0,
                }
            ],
            "more_available": True,
            "next_max_id": "cursor123",
        }
    }

    result = _normalize_posts_response(resp, "testuser")

    assert len(result["contents"]) == 1
    assert result["more_available"] is True
    assert result["next_cursor"] == "cursor123"
    assert result["contents"][0]["content_type"] == "post"


# Check that empty or invalid reels are filtered out
def test_normalize_reels_response_filters_empty():
    resp = {
        "data": {
            "items": [
                {"media": {}},
                {
                    "media": {
                        "video_versions": [{"url": "http://reel.mp4"}],
                        "taken_at": 0,
                        "caption": "",
                    }
                },
            ],
            "paging_info": {
                "more_available": False,
                "max_id": None,
            },
        }
    }

    result = _normalize_reels_response(resp, "testuser")

    assert len(result["contents"]) == 1
    assert result["contents"][0]["content_type"] == "reel"
    assert result["contents"][0]["media_content"][0]["original_url"] == "http://reel.mp4"


# Check that reel pagination info is picked up correctly
def test_normalize_reels_response_pagination():
    resp = {
        "data": {
            "items": [],
            "paging_info": {
                "more_available": True,
                "max_id": "reel_cursor_123",
            },
        }
    }

    result = _normalize_reels_response(resp, "testuser")

    assert result["more_available"] is True
    assert result["next_cursor"] == "reel_cursor_123"
