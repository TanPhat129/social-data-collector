from datetime import datetime
from pydantic import BaseModel, Field


class Source(BaseModel):
    id: str
    name: str
    platform: str = "facebook"
    external_id: str | None = None
    source_url: str | None = None
    enabled: bool = True


class RawPost(BaseModel):
    post_id: str
    source: Source
    content: str
    posted_at: datetime | None = None
    post_url: str | None = None
    collected_at: datetime = Field(default_factory=datetime.now)


class TutorLead(BaseModel):
    post_id: str
    collected_at: datetime
    posted_at: datetime | None
    platform: str
    group: str
    subject: str | None = None
    grade: str | None = None
    location: str | None = None
    mode: str | None = None
    schedule: str | None = None
    frequency: str | None = None
    budget: str | None = None
    phone: str | None = None
    content: str
    post_url: str | None = None
    confidence: float = Field(ge=0, le=1)
