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
TIMEOUT_SECONDS = 60


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
    logging.debug("RAW RESPONSE:", response.json())

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
    media = item.get("media")
    if isinstance(media, dict):
        return _extract_best_image(media)
    return None


def _extract_best_video(item: Dict[str, Any]) -> Optional[str]:
    versions = _as_list(item.get("video_versions"))
    if versions:
        return versions[0].get("url")
    if item.get("video_url"):
        return item.get("video_url")
    media = item.get("media")
    if isinstance(media, dict):
        return _extract_best_video(media)
    return None


def _extract_caption(item: Dict[str, Any]) -> str:
    caption = item.get("caption")
    if isinstance(caption, dict):
        return caption.get("text", "") or ""
    if isinstance(caption, str):
        return caption
    if item.get("caption_text"):
        return item.get("caption_text", "")
    media = item.get("media")
    if isinstance(media, dict):
        return _extract_caption(media)
    return ""


def _extract_taken_at(item: Dict[str, Any]) -> Any:
    if item.get("taken_at") is not None:
        return item.get("taken_at")
    media = item.get("media")
    if isinstance(media, dict):
        return media.get("taken_at")
    return None


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
        "datetime": _to_iso8601(_extract_taken_at(item)),
        "content_type": "post",
        "media_content": media_content,
    }


def _normalize_reel(item: Dict[str, Any], identifier: str):
    media_obj = item.get("media") if isinstance(item.get("media"), dict) else item
    video_url = _extract_best_video(media_obj)
    thumbnail = _extract_best_image(media_obj)

    if not video_url:
        return None

    return {
        "error_message": "",
        "owners": [identifier],
        "caption": _extract_caption(media_obj),
        "datetime": _to_iso8601(_extract_taken_at(media_obj)),
        "content_type": "reel",
        "media_content": [
            {
                "media_type": "video",
                "original_url": video_url,
                "original_thumbnail_url": thumbnail or "",
            }
        ],
    }


def _normalize_posts_response(posts_resp: Dict[str, Any], identifier: str) -> Dict[str, Any]:
    items = (
        _as_list(_safe_get(posts_resp, "data", "items"))
        or _as_list(_safe_get(posts_resp, "data", "data", "items"))
        or _as_list(_safe_get(posts_resp, "items"))
    )
    contents = [_normalize_post(item, identifier) for item in items]

    more_available = bool(_safe_get(posts_resp, "data", "more_available", default=False))
    next_cursor = _safe_get(posts_resp, "data", "next_max_id")

    return {
        "contents": contents,
        "more_available": more_available,
        "next_cursor": next_cursor,
    }


def _normalize_reels_response(reels_resp: Dict[str, Any], identifier: str) -> Dict[str, Any]:
    items = (
        _as_list(_safe_get(reels_resp, "data", "items"))
        or _as_list(_safe_get(reels_resp, "data", "data", "items"))
        or _as_list(_safe_get(reels_resp, "items"))
    )

    contents: List[Dict[str, Any]] = []
    for item in items:
        reel = _normalize_reel(item, identifier)
        if reel:
            contents.append(reel)

    more_available = bool(_safe_get(reels_resp, "data", "paging_info", "more_available", default=False))
    next_cursor = _safe_get(reels_resp, "data", "paging_info", "max_id")

    return {
        "contents": contents,
        "more_available": more_available,
        "next_cursor": next_cursor,
    }


def trigger_external(
    identifier: str,
    case_id: str,
    artifact_id: str,
    content_type: Optional[str] = None,
    cursor: Optional[str] = None,
    instagram_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    logging.info(
        "external_api:trigger_external was triggered for identifier=%s case_id=%s artifact_id=%s content_type=%s cursor=%s",
        identifier,
        case_id,
        artifact_id,
        content_type,
        cursor,
    )

    # pagination mode
    if content_type == "post":
        params = {"handle": identifier}
        if cursor:
            params["next_max_id"] = cursor

        posts_resp = _get("posts", params)
        posts_data = _normalize_posts_response(posts_resp, identifier)

        return {
            "status": "success",
            "results": {
                "metadata": {
                    "platform": "instagram",
                    "identifier": identifier,
                    "description": f"Instagram Profile of {identifier}",
                    "next_post_cursor": posts_data["next_cursor"],
                    "next_reel_cursor": None,
                    "instagram_user_id": instagram_user_id,
                },
                "has_more_data": [
                    {"content_type": "post", "has_more_data": posts_data["more_available"]},
                    {"content_type": "reel", "has_more_data": False},
                ],
                "contents": posts_data["contents"],
            },
        }

    if content_type == "reel":
        params = {}
        if instagram_user_id:
            params["user_id"] = instagram_user_id
        else:
            params["handle"] = identifier
        if cursor:
            params["max_id"] = cursor

        reels_resp = _get("reels", params)
        reels_data = _normalize_reels_response(reels_resp, identifier)

        return {
            "status": "success",
            "results": {
                "metadata": {
                    "platform": "instagram",
                    "identifier": identifier,
                    "description": f"Instagram Profile of {identifier}",
                    "next_post_cursor": None,
                    "next_reel_cursor": reels_data["next_cursor"],
                    "instagram_user_id": instagram_user_id,
                },
                "has_more_data": [
                    {"content_type": "post", "has_more_data": False},
                    {"content_type": "reel", "has_more_data": reels_data["more_available"]},
                ],
                "contents": reels_data["contents"],
            },
        }

    # initial fetch mode
    params = {"handle": identifier}
    profile_resp = _get("profile", params)
    posts_resp = _get("posts", params)

    try:
        reels_resp = _get("reels", params)
        reels_data = _normalize_reels_response(reels_resp, identifier)
    except Exception as e:
        logging.warning(f"Reels fetch failed, continuing without reels: {e}")
        reels_data = {"contents": [], "more_available": False, "next_cursor": None}

    user = (
        _safe_get(profile_resp, "data", "data", "user")
        or _safe_get(profile_resp, "data", "user")
        or {}
    )

    posts_data = _normalize_posts_response(posts_resp, identifier)
    reels_data = _normalize_reels_response(reels_resp, identifier)

    contents: List[Dict[str, Any]] = []
    contents.extend(posts_data["contents"])
    contents.extend(reels_data["contents"])

    return {
        "status": "success",
        "results": {
            "metadata": {
                "platform": "instagram",
                "identifier": user.get("username") or identifier,
                "display_name": user.get("full_name") or identifier,
                "profile_pic": user.get("profile_pic_url_hd") or user.get("profile_pic_url"),
                "description": user.get("biography") or f"Instagram Profile of {identifier}",
                "instagram_user_id": user.get("id"),
                "next_post_cursor": posts_data["next_cursor"],
                "next_reel_cursor": reels_data["next_cursor"],
            },
            "has_more_data": [
                {"content_type": "post", "has_more_data": posts_data["more_available"]},
                {"content_type": "reel", "has_more_data": reels_data["more_available"]},
            ],
            "contents": contents,
        },
    }