"""Request/response models for the JSON API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    plan: str
    credits: int


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    niche: str = ""
    language: str = "en"
    voice_id: str = ""
    avatar_id: str = ""
    aspect_ratio: str = "16:9"
    target_duration_seconds: int = Field(default=480, ge=15, le=3600)
    style_profile: dict = Field(default_factory=dict)


class ChannelOut(ChannelIn):
    id: int
    youtube_connected: bool
    created_at: datetime


class RunIn(BaseModel):
    channel_id: int
    topic: str = Field(min_length=3, max_length=500)
    pipeline: str = "faceless_longform"
    options: dict = Field(default_factory=dict)


class NodeOut(BaseModel):
    id: int
    key: str
    type: str
    title: str
    status: str
    depends_on: list[str]
    requires_approval: bool
    attempts: int
    credits_spent: int
    error: str | None = None
    output: dict = Field(default_factory=dict)
    review_feedback: str | None = None


class ArtifactOut(BaseModel):
    id: int
    kind: str
    mime: str
    size_bytes: int
    node_key: str | None = None
    url: str | None = None
    meta: dict = Field(default_factory=dict)


class RunOut(BaseModel):
    id: int
    channel_id: int
    topic: str
    pipeline: str
    status: str
    credits_reserved: int
    credits_spent: int
    error: str | None = None
    created_at: datetime
    finished_at: datetime | None = None
    nodes: list[NodeOut] = Field(default_factory=list)
    artifacts: list[ArtifactOut] = Field(default_factory=list)


class GateIn(BaseModel):
    """Approve, or reject with feedback. Sending `feedback` means reject."""

    feedback: str | None = None
    note: str = ""
    overrides: dict | None = None


class EventOut(BaseModel):
    id: int
    node_key: str | None
    level: str
    message: str
    data: dict
    created_at: datetime


class ProviderKeyIn(BaseModel):
    provider: str = Field(min_length=2, max_length=64)
    api_key: str = Field(min_length=8, max_length=500)


class ProviderKeyOut(BaseModel):
    id: int
    provider: str
    masked: str
    fingerprint: str
    created_at: datetime


class CreditsOut(BaseModel):
    balance: int
    balance_usd: float
    plan: str
    entries: list[dict]


class EstimateOut(BaseModel):
    pipeline: str
    total_credits: int
    total_usd: float
    per_node: list[dict]
