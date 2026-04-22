"""
This module defines the external API controller logic for processing requests and returning results.
It calls SociaVault's Instagram endpoints and normalizes the response into the shape expected by the app.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests


BASE_URL = "https://api.sociavault.com/v1/scrape/instagram"
TIMEOUT_SECONDS = 30


def _get_api_key() -> str:
    api_key = os.getenv("SOCIAVAULT_API_KEY")
    if not api_key:
        raise ValueError(
            "Missing SOCIAVAULT_API_KEY. "
            "Create a free SociaVault account and set the API key in your environment."
        )
    return api_key


def _headers() -> Dict[str, str]:
    return {
        "X-API-Key": _get_api_key(),
        "Accept": "application/json",
    }


def _get(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE_URL}/{endpoint}"
    logging.info("Calling SociaVault endpoint: %s with params=%s", url, params)

    response = requests.get(
        url,
        headers=_headers(),
        params=params,
        timeout=TIMEOUT_SECONDS,
    )

    if response.status_code >= 400:
        raise RuntimeError(
            f"SociaVault API call failed for {endpoint}: "
            f"{response.status_code} {response.text}"
        )

    return response.json()


def _safe_get(d: Any, *keys: Any, default=None):
    current = d
    for key in keys:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return default
    return current if current is not None else default


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def _to_iso8601(value: Any) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, (int, float)):
            return datetime.utcfromtimestamp(value).isoformat() + "Z"
        return str(value)
    except Exception:
        return str(value)


def _extract_best_image(item: Dict[str, Any]) -> Optional[str]:
    candidates = _as_list(_safe_get(item, "image_versions2", "candidates", default=[]))
    if candidates:
        return candidates[0].get("url")
    if item.get("display_url"):
        return item.get("display_url")
    if item.get("thumbnail_url"):
        return item.get("thumbnail_url")
    return None


def _extract_best_video(item: Dict[str, Any]) -> Optional[str]:
    versions = _as_list(item.get("video_versions"))
    if versions:
        return versions[0].get("url")
    if item.get("video_url"):
        return item.get("video_url")
    return None


def _extract_caption(item: Dict[str, Any]) -> str:
    caption = item.get("caption")
    if isinstance(caption, dict):
        return caption.get("text", "") or ""
    if isinstance(caption, str):
        return caption
    if item.get("caption_text"):
        return item.get("caption_text", "")
    return ""


def _normalize_post(item: Dict[str, Any], identifier: str) -> Dict[str, Any]:
    media_type = item.get("media_type")
    media_content: List[Dict[str, Any]] = []

    if media_type == 8:
        carousel_items = _as_list(item.get("carousel_media"))
        for child in carousel_items:
            child_media_type = child.get("media_type")
            if child_media_type == 2:
                media_content.append({
                    "media_type": "video",
                    "original_url": _extract_best_video(child) or "",
                    "original_thumbnail_url": _extract_best_image(child) or "",
                })
            else:
                media_content.append({
                    "media_type": "image",
                    "original_url": _extract_best_image(child) or "",
                })
    elif media_type == 2:
        media_content.append({
            "media_type": "video",
            "original_url": _extract_best_video(item) or "",
            "original_thumbnail_url": _extract_best_image(item) or "",
        })
    else:
        media_content.append({
            "media_type": "image",
            "original_url": _extract_best_image(item) or "",
        })

    return {
        "error_message": "",
        "owners": [identifier],
        "caption": _extract_caption(item),
        "datetime": _to_iso8601(item.get("taken_at")),
        "content_type": "post",
        "media_content": media_content,
    }


def _normalize_reel(item: Dict[str, Any], identifier: str) -> Dict[str, Any]:
    return {
        "error_message": "",
        "owners": [identifier],
        "caption": _extract_caption(item),
        "datetime": _to_iso8601(item.get("taken_at")),
        "content_type": "reel",
        "media_content": [
            {
                "media_type": "video",
                "original_url": _extract_best_video(item) or "",
                "original_thumbnail_url": _extract_best_image(item) or "",
            }
        ],
    }

def _normalize_reel(item, identifier):
    video_url = _extract_best_video(item)
    thumbnail = _extract_best_image(item)

    # 🚫 skip empty reels
    if not video_url:
        return None

    return {
        "error_message": "",
        "owners": [identifier],
        "caption": _extract_caption(item),
        "datetime": _to_iso8601(item.get("taken_at")),
        "content_type": "reel",
        "media_content": [
            {
                "media_type": "video",
                "original_url": video_url,
                "original_thumbnail_url": thumbnail or "",
            }
        ],
    }

def trigger_external(identifier: str, case_id: str, artifact_id: str) -> Dict[str, Any]:
    logging.info(
        "external_api:trigger_external was triggered for identifier=%s case_id=%s artifact_id=%s",
        identifier,
        case_id,
        artifact_id,
    )

    params = {"handle": identifier}

    profile_resp = _get("profile", params)
    posts_resp = _get("posts", params)
    reels_resp = _get("reels", params)

    user = (
        _safe_get(profile_resp, "data", "data", "user")
        or _safe_get(profile_resp, "data", "user")
        or {}
    )

    post_items = (
        _as_list(_safe_get(posts_resp, "data", "items"))
        or _as_list(_safe_get(posts_resp, "data", "data", "items"))
        or _as_list(_safe_get(posts_resp, "items"))
    )

    reel_items = (
        _as_list(_safe_get(reels_resp, "data", "items"))
        or _as_list(_safe_get(reels_resp, "data", "data", "items"))
        or _as_list(_safe_get(reels_resp, "items"))
    )

    contents: List[Dict[str, Any]] = []
    contents.extend(_normalize_post(item, identifier) for item in post_items)
    contents.extend(_normalize_reel(item, identifier) for item in reel_items)

    return {
        "status": "success",
        "results": {
            "metadata": {
                "platform": "instagram",
                "identifier": user.get("username") or identifier,
                "display_name": user.get("full_name") or identifier,
                "profile_pic": user.get("profile_pic_url_hd") or user.get("profile_pic_url"),
                "description": user.get("biography") or f"Instagram Profile of {identifier}",
            },
            "contents": contents,
        },

        
    }