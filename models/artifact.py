"""
This module defines the data models for artifact metadata and content using Pydantic.
"""
from datetime import UTC, datetime
from typing import List, Optional
from pydantic import BaseModel, Field

class ArtifactMetadata(BaseModel):
    artifact_id: str
    case_id: str
    description: str
    identifier: str
    platform: str="instagram"
    display_name: Optional[str] = None
    profile_pic: Optional[str] = None
    created_datetime: str = Field(default_factory = lambda: datetime.now(UTC).isoformat())
    status: str = "processing"


class MediaContent(BaseModel):
    media_type: str
    original_url: str
    original_thumbnail_url: Optional[str] = None
    url: Optional[str] = None
    thumbnail_url: Optional[str] = None


class ArtifactContent(BaseModel):
    artifact_id: str
    error_message: str = ""
    owners: List[str] = []
    caption: str = ""
    datetime: str
    content_type: str
    media_content: List[MediaContent] = []
