"""
This module defines the database interaction functions for managing artifact metadata and results.
It includes functions for creating artifact metadata, updating results, and updating metadata status.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("artifacts.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS artifacts (
        artifact_id TEXT PRIMARY KEY,
        case_id TEXT NOT NULL,
        identifier TEXT NOT NULL,
        description TEXT NOT NULL,
        platform TEXT NOT NULL DEFAULT 'instagram',
        display_name TEXT,
        profile_pic TEXT,
        instagram_user_id TEXT,
        next_post_cursor TEXT,
        next_reel_cursor TEXT,
        has_more_posts INTEGER NOT NULL DEFAULT 0,
        has_more_reels INTEGER NOT NULL DEFAULT 0,
        created_datetime TEXT NOT NULL,
        status TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS contents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        artifact_id TEXT NOT NULL,
        error_message TEXT,
        owners_json TEXT,
        caption TEXT,
        datetime TEXT,
        content_type TEXT,
        media_content_json TEXT,
        FOREIGN KEY (artifact_id) REFERENCES artifacts (artifact_id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blobs (
        blob_id TEXT PRIMARY KEY,
        artifact_id TEXT NOT NULL,
        original_url TEXT NOT NULL,
        local_path TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        FOREIGN KEY (artifact_id) REFERENCES artifacts (artifact_id)
    )
    """)

    conn.commit()
  # lightweight migration support if table already existed
    existing_cols = {
        row["name"] for row in cur.execute("PRAGMA table_info(artifacts)").fetchall()
    }

    alter_statements = {
        "instagram_user_id": "ALTER TABLE artifacts ADD COLUMN instagram_user_id TEXT",
        "next_post_cursor": "ALTER TABLE artifacts ADD COLUMN next_post_cursor TEXT",
        "next_reel_cursor": "ALTER TABLE artifacts ADD COLUMN next_reel_cursor TEXT",
        "has_more_posts": "ALTER TABLE artifacts ADD COLUMN has_more_posts INTEGER NOT NULL DEFAULT 0",
        "has_more_reels": "ALTER TABLE artifacts ADD COLUMN has_more_reels INTEGER NOT NULL DEFAULT 0",
    }

    for col, stmt in alter_statements.items():
        if col not in existing_cols:
            cur.execute(stmt)

    conn.commit()
    conn.close()


def create_artifact_metadata(artifact_id, case_id, identifier, description) -> None:
    logging.info("db:create_artifact_metadata was triggered")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO artifacts (
            artifact_id, case_id, identifier, description,
            platform, created_datetime, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        artifact_id,
        case_id,
        identifier,
        description,
        "instagram",
        datetime.utcnow().isoformat(),
        "processing"
    ))
    conn.commit()
    conn.close()


def update_metadata_status(artifact_id, case_id, status):
    logging.info("db:update_metadata_status was triggered")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE artifacts
        SET status = ?
        WHERE artifact_id = ? AND case_id = ?
    """, (status, artifact_id, case_id))
    conn.commit()
    conn.close()


def update_results(artifact_id, content, append=False):
    import blob_service  # import here to avoid circular imports
    logging.info("db:update_results was triggered")
    conn = get_conn()
    cur = conn.cursor()

    metadata = content.get("metadata", {})
    contents = content.get("contents", [])
    has_more_data = content.get("has_more_data", [])
    has_more_map = {item["content_type"]: item["has_more_data"]
                    for item in has_more_data}

    cur.execute("""
        UPDATE artifacts
        SET display_name = ?, profile_pic = ?, instagram_user_id = ?,
            next_post_cursor = ?, next_reel_cursor = ?,
            has_more_posts = ?, has_more_reels = ?
        WHERE artifact_id = ?
    """, (
        metadata.get("display_name"), metadata.get("profile_pic"),
        metadata.get("instagram_user_id"), metadata.get("next_post_cursor"),
        metadata.get("next_reel_cursor"),
        1 if has_more_map.get("post", False) else 0,
        1 if has_more_map.get("reel", False) else 0,
        artifact_id
    ))

    if not append:
        cur.execute("DELETE FROM contents WHERE artifact_id = ?",
                    (artifact_id,))

    for item in contents:
        # download each media file and add blob url
        updated_media = []
        for media in item.get("media_content", []):
            updated = dict(media)
            original_url = media.get("original_url", "")
            if original_url:
                blob_id, local_path, mime_type = blob_service.download_and_save(
                    original_url, artifact_id
                )
                if blob_id:
                    updated["url"] = f"/api/blob/{blob_id}"
                    save_blob(cur, blob_id, artifact_id,
                              original_url, local_path, mime_type)

            # handle thumbnail too
            thumb_url = media.get("original_thumbnail_url", "")
            if thumb_url:
                blob_id, local_path, mime_type = blob_service.download_and_save(
                    thumb_url, artifact_id
                )
                if blob_id:
                    updated["thumbnail_url"] = f"/api/blob/{blob_id}"
                    save_blob(cur, blob_id, artifact_id,
                              thumb_url, local_path, mime_type)

            updated_media.append(updated)

        cur.execute("""
            INSERT INTO contents (
                artifact_id, error_message, owners_json, caption,
                datetime, content_type, media_content_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            artifact_id,
            item.get("error_message", ""),
            json.dumps(item.get("owners", [])),
            item.get("caption", ""),
            item.get("datetime", ""),
            item.get("content_type", ""),
            json.dumps(updated_media)
        ))

    conn.commit()
    conn.close()
    return content


def build_response(artifact, contents):
    artifact = dict(artifact)

    has_more_data = [
        {
            "content_type": "post",
            "has_more_data": bool(artifact.get("has_more_posts"))
        },
        {
            "content_type": "reel",
            "has_more_data": bool(artifact.get("has_more_reels"))
        }
    ]

    response = {
        "status": artifact["status"],
        "has_more_data": has_more_data,
        "metadata": {
            "platform": artifact["platform"],
            "identifier": artifact["identifier"],
            "description": artifact["description"]
        },
        "contents": []
    }

    if artifact.get("display_name"):
        response["metadata"]["display_name"] = artifact["display_name"]

    if artifact.get("profile_pic"):
        response["metadata"]["profile_pic"] = artifact["profile_pic"]

    for row in contents:
        row = dict(row)
        response["contents"].append({
            "error_message": row["error_message"] or "",
            "owners": json.loads(row["owners_json"] or "[]"),
            "caption": row["caption"] or "",
            "datetime": row["datetime"],
            "content_type": row["content_type"],
            "media_content": json.loads(row["media_content_json"] or "[]")
        })

    return response


def get_artifact_row(artifact_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,))
    row = cur.fetchone()
    conn.close()
    return row


def get_artifact_by_id(artifact_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,))
    artifact = cur.fetchone()

    if not artifact:
        conn.close()
        return None

    cur.execute("SELECT * FROM contents WHERE artifact_id = ?", (artifact_id,))
    contents = cur.fetchall()
    conn.close()

    return build_response(artifact, contents)


def list_artifacts():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM artifacts ORDER BY created_datetime DESC")
    artifacts = cur.fetchall()

    results = []
    for artifact in artifacts:
        cur.execute("SELECT * FROM contents WHERE artifact_id = ?",
                    (artifact["artifact_id"],))
        contents = cur.fetchall()
        results.append(build_response(artifact, contents))

    conn.close()
    return results


def find_in_progress_artifact(case_id, identifier):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT artifact_id
        FROM artifacts
        WHERE case_id = ? AND identifier = ? AND status = 'processing'
        ORDER BY created_datetime DESC
        LIMIT 1
    """, (case_id, identifier))
    row = cur.fetchone()
    conn.close()
    return row["artifact_id"] if row else None


def get_pagination_context(artifact_id, content_type):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT artifact_id, identifier, instagram_user_id, next_post_cursor, next_reel_cursor
        FROM artifacts
        WHERE artifact_id = ?
    """, (artifact_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    row = dict(row)
    return {
        "artifact_id": row["artifact_id"],
        "identifier": row["identifier"],
        "instagram_user_id": row["instagram_user_id"],
        "cursor": row["next_post_cursor"] if content_type == "post" else row["next_reel_cursor"],
    }


def save_blob(cur, blob_id, artifact_id, original_url, local_path, mime_type):
    cur.execute("""
        INSERT OR IGNORE INTO blobs (blob_id, artifact_id, original_url, local_path, mime_type)
        VALUES (?, ?, ?, ?, ?)
    """, (blob_id, artifact_id, original_url, local_path, mime_type))


def get_blob(blob_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM blobs WHERE blob_id = ?", (blob_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None
