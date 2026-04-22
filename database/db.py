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


def update_results(artifact_id, content):
    logging.info("db:update_results was triggered")
    conn = get_conn()
    cur = conn.cursor()

    metadata = content.get("metadata", {})
    contents = content.get("contents", [])

    cur.execute("""
        UPDATE artifacts
        SET display_name = ?, profile_pic = ?
        WHERE artifact_id = ?
    """, (
        metadata.get("display_name"),
        metadata.get("profile_pic"),
        artifact_id
    ))

    for item in contents:
        cur.execute("""
            INSERT INTO contents (
                artifact_id, error_message, owners_json, caption,
                datetime, content_type, media_content_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            artifact_id,
            item.get("error_message", ""),
            json.dumps(item.get("owners", [])),
            item.get("caption", ""),
            item.get("datetime", ""),
            item.get("content_type", ""),
            json.dumps(item.get("media_content", []))
        ))

    conn.commit()
    conn.close()
    return content


def build_response(artifact, contents):
    artifact = dict(artifact)

    response = {
        "status": artifact["status"],
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
        cur.execute("SELECT * FROM contents WHERE artifact_id = ?", (artifact["artifact_id"],))
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