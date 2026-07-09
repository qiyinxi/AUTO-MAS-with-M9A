from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .schema import OutBase


class ScriptTypeDescriptor(BaseModel):
    """Script type descriptor."""

    type_key: str = Field(..., description="Script type key")
    display_name: str = Field(..., description="Display name")
    icon: str | None = Field(default=None, description="Icon id")
    icon_url: str | None = Field(default=None, description="Icon resource URL")
    theme_color: str | None = Field(default=None, description="Theme color for UI tags")
    docs_url: str | None = Field(default=None, description="Docs URL")
    editor_kind: str = Field(..., description="Editor kind")
    supported_modes: list[str] = Field(..., description="Supported task modes")
    script_schema: dict[str, Any] = Field(..., description="Script form schema")
    user_schema: dict[str, Any] = Field(..., description="User form schema")
    legacy_config_class_name: str | None = Field(
        default=None,
        description="Legacy script config class name",
    )
    legacy_user_config_class_name: str | None = Field(
        default=None,
        description="Legacy user config class name",
    )
    is_builtin: bool = Field(default=False, description="Whether this is a built-in script type")
    available: bool = Field(default=True, description="Whether this type is currently available")


class ScriptTypeGetOut(OutBase):
    data: list[ScriptTypeDescriptor] = Field(..., description="Script type descriptors")


class ScriptRecord(BaseModel):
    """Generic script record."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="Script ID")
    type: str = Field(..., description="Script type key")
    name: str = Field(..., description="Script name")
    config: dict[str, Any] = Field(..., description="Script config payload")
    schema_definition: dict[str, Any] = Field(
        ...,
        alias="schema",
        serialization_alias="schema",
        description="Script form schema",
    )
    editor_kind: str = Field(..., description="Editor kind")
    supported_modes: list[str] = Field(..., description="Supported task modes")
    icon: str | None = Field(default=None, description="Icon id")
    icon_url: str | None = Field(default=None, description="Icon resource URL")
    theme_color: str | None = Field(default=None, description="Theme color for UI tags")
    docs_url: str | None = Field(default=None, description="Docs URL")
    edit_hint: dict[str, Any] | None = Field(
        default=None,
        description="Optional hint shown at the bottom of the script edit page",
    )
    user_count: int = Field(default=0, description="User count")


class ScriptRecordGetIn(BaseModel):
    scriptId: str | None = Field(default=None, description="Script ID")


class ScriptRecordCreateIn(BaseModel):
    type: str = Field(..., description="Script type key")
    scriptId: str | None = Field(default=None, description="Source script ID for copy")


class ScriptRecordUpdateIn(BaseModel):
    scriptId: str = Field(..., description="Script ID")
    config: dict[str, Any] = Field(..., description="Script config patch")


class ScriptRecordDeleteIn(BaseModel):
    scriptId: str = Field(..., description="Script ID")


class ScriptRecordReorderIn(BaseModel):
    indexList: list[str] = Field(..., description="Script ID order")


class ScriptRecordCreateOut(OutBase):
    record: ScriptRecord = Field(..., description="Created script record")


class ScriptRecordGetOut(OutBase):
    records: list[ScriptRecord] = Field(..., description="Script records")


class ScriptUserRecord(BaseModel):
    """Generic script user record."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="User ID")
    script_id: str = Field(..., description="Owner script ID")
    type: str = Field(..., description="Script type key")
    name: str = Field(..., description="User name")
    config: dict[str, Any] = Field(..., description="User config payload")
    schema_definition: dict[str, Any] = Field(
        ...,
        alias="schema",
        serialization_alias="schema",
        description="User form schema",
    )


class ScriptUserRecordGetIn(BaseModel):
    scriptId: str = Field(..., description="Owner script ID")
    userId: str | None = Field(default=None, description="User ID")


class ScriptUserRecordCreateIn(BaseModel):
    scriptId: str = Field(..., description="Owner script ID")


class ScriptUserRecordUpdateIn(BaseModel):
    scriptId: str = Field(..., description="Owner script ID")
    userId: str = Field(..., description="User ID")
    config: dict[str, Any] = Field(..., description="User config patch")


class ScriptUserRecordDeleteIn(BaseModel):
    scriptId: str = Field(..., description="Owner script ID")
    userId: str = Field(..., description="User ID")


class ScriptUserRecordReorderIn(BaseModel):
    scriptId: str = Field(..., description="Owner script ID")
    indexList: list[str] = Field(..., description="User ID order")


class ScriptUserRecordCreateOut(OutBase):
    record: ScriptUserRecord = Field(..., description="Created user record")


class ScriptUserRecordGetOut(OutBase):
    records: list[ScriptUserRecord] = Field(..., description="User records")
