import hashlib
import logging
import mimetypes
import os
import uuid
import requests
from pathlib import Path

BLOB_DIR = Path("blobs")
BLOB_DIR.mkdir(exist_ok=True)

def _guess_mime(url: str) -> str:
    ext = url.split("?")[0].split(".")[-1].lower()
    mapping = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "webp": "image/webp",
        "gif": "image/gif", "mp4": "video/mp4",
        "mov": "video/quicktime",
    }
    return mapping.get(ext, "application/octet-stream")

def download_and_save(original_url: str, artifact_id: str) -> tuple:
    """Downloads a file and returns (blob_id, local_path, mime_type)."""
    blob_id = hashlib.md5(original_url.encode()).hexdigest()
    mime_type = _guess_mime(original_url)
    ext = mime_type.split("/")[-1].replace("jpeg", "jpg")
    local_path = BLOB_DIR / f"{blob_id}.{ext}"

    if not local_path.exists():
        try:
            response = requests.get(original_url, timeout=30, stream=True)
            response.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            logging.info(f"Downloaded blob {blob_id} from {original_url}")
        except Exception as e:
            logging.error(f"Failed to download {original_url}: {e}")
            return None, None, None

    return blob_id, str(local_path), mime_type