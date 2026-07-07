from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class M9APeriodRule(BaseModel):
    task: str
    period: Literal["weekly", "monthly"]


class M9APackDefinition(BaseModel):
    key: str = "m9a"
    displayName: str = "M9A"
    framework: str = "maafw"
    periodRules: list[M9APeriodRule] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)


class M9ANotificationContent(BaseModel):
    title: str
    text: str
    html: str | None = None


class M9AMigrationDraft(BaseModel):
    script: dict[str, Any]
    users: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
