from __future__ import annotations

from pathlib import Path
from typing import Any

import json5
from pydantic import BaseModel, Field

from .models import MaaFWInterface
from .task_config import _build_task_option_maps, build_interface_preset_snapshot


class MaaFWInterfaceValidationReport(BaseModel):
    ok: bool
    message: str = ""


class MaaFWInterfacePreviewData(BaseModel):
    path: str
    project: dict[str, Any]
    globalOption: list[str] = Field(default_factory=list)
    controllers: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    groups: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    options: list[dict[str, Any]] = Field(default_factory=list)
    presets: list[dict[str, Any]] = Field(default_factory=list)
    importCount: int = 0
    agentCount: int = 0


def build_interface_preview_data(
    root_path: str | Path,
    interface: MaaFWInterface,
) -> MaaFWInterfacePreviewData:
    root = Path(root_path).resolve()
    i18n_mapping = _load_i18n_mapping(root, interface)
    task_order = [task.name for task in interface.task]
    task_option_maps = _build_task_option_maps(interface)

    def tr_text(value: str | None) -> str | None:
        translated = _resolve_i18n_value(value, i18n_mapping)
        return translated if isinstance(translated, str) else value

    def tr_description(value: str | None) -> str | None:
        return resolve_description(root, tr_text(value))

    agent_count = 0
    if isinstance(interface.agent, list):
        agent_count = len(interface.agent)
    elif interface.agent is not None:
        agent_count = 1

    presets: list[dict[str, Any]] = []
    for preset in interface.preset:
        snapshot = build_interface_preset_snapshot(
            interface,
            preset,
            task_order=task_order,
            task_option_maps=task_option_maps,
            include_default_options=False,
        )
        checked_count = sum(1 for checked in snapshot.taskChecked.values() if checked)
        presets.append(
            {
                "name": preset.name,
                "label": tr_text(preset.label),
                "description": tr_description(preset.description),
                "taskCount": len(preset.task or []),
                "checkedCount": checked_count,
                "snapshot": snapshot.model_dump(mode="json"),
            }
        )

    return MaaFWInterfacePreviewData(
        path=str(root),
        project={
            "name": interface.name,
            "label": tr_text(interface.label),
            "title": tr_text(interface.title),
            "version": interface.version,
            "github": interface.github,
            "mirrorchyanRid": interface.mirrorchyan_rid,
            "mirrorchyanMultiplatform": interface.mirrorchyan_multiplatform,
            "description": tr_description(interface.description),
            "icon": interface.icon,
        },
        globalOption=interface.global_option or [],
        controllers=[
            {
                "name": controller.name,
                "label": tr_text(controller.label),
                "type": controller.type,
                "description": tr_description(controller.description),
                "icon": controller.icon,
                "option": controller.option or [],
                "permissionRequired": bool(controller.permission_required),
            }
            for controller in interface.controller
        ],
        resources=[
            {
                "name": resource.name,
                "label": tr_text(resource.label),
                "description": tr_description(resource.description),
                "icon": resource.icon,
                "path": resource.path,
                "controller": resource.controller or [],
                "option": resource.option or [],
            }
            for resource in interface.resource
        ],
        groups=[
            {
                "name": group.name,
                "label": tr_text(group.label),
                "description": tr_description(group.description),
                "icon": group.icon,
                "defaultExpand": bool(group.default_expand),
            }
            for group in interface.group or []
        ],
        tasks=[
            {
                "name": task.name,
                "label": tr_text(task.label),
                "entry": task.entry,
                "description": tr_description(task.description),
                "icon": task.icon,
                "group": task.group or [],
                "controller": task.controller or [],
                "resource": task.resource or [],
                "option": task.option or [],
                "defaultCheck": bool(task.default_check),
            }
            for task in interface.task
        ],
        options=[
            {
                "name": option_name,
                "type": option.type,
                "label": tr_text(option.label),
                "description": tr_description(option.description),
                "icon": option.icon,
                "controller": option.controller or [],
                "resource": option.resource or [],
                "cases": [
                    {
                        "name": case.name,
                        "label": tr_text(case.label),
                        "description": tr_description(case.description),
                        "icon": case.icon,
                        "option": case.option or [],
                    }
                    for case in option.cases or []
                ],
                "inputs": [
                    {
                        "name": input_item.name,
                        "label": tr_text(input_item.label),
                        "description": tr_description(input_item.description),
                        "icon": input_item.icon,
                        "default": input_item.default,
                        "pipelineType": input_item.pipeline_type,
                        "verify": input_item.verify,
                        "verifyError": input_item.verify_error,
                        "patternMsg": input_item.pattern_msg,
                    }
                    for input_item in option.inputs or []
                ],
                "defaultCase": option.default_case,
            }
            for option_name, option in interface.option.items()
        ],
        presets=presets,
        importCount=len(interface.import_ or []),
        agentCount=agent_count,
    )


def resolve_description(root_path: Path, description: str | None) -> str | None:
    if not isinstance(description, str):
        return description

    raw_description = description.strip()
    if not raw_description or "\n" in raw_description or raw_description.startswith("<"):
        return description
    if raw_description.startswith(("http://", "https://")):
        return description

    description_path = Path(raw_description)
    if description_path.is_absolute() or ".." in description_path.parts:
        return description

    try:
        root = root_path.resolve()
        resolved_path = (root / description_path).resolve()
        resolved_path.relative_to(root)
    except Exception:
        return description

    if not resolved_path.is_file():
        return description
    if resolved_path.suffix.lower() not in {".md", ".markdown", ".txt"}:
        return description

    try:
        if resolved_path.stat().st_size > 512 * 1024:
            return description
        return resolved_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return resolved_path.read_text(encoding="utf-8-sig")
        except Exception:
            return description
    except Exception:
        return description


def _load_i18n_mapping(root_path: Path, interface: MaaFWInterface) -> dict[str, Any]:
    if not interface.languages:
        return {}

    language_file = interface.languages.get("zh_cn")
    if not isinstance(language_file, str) or not language_file.strip():
        return {}

    language_path = _resolve_project_path(root_path, language_file)
    if language_path is None or not language_path.is_file():
        return {}

    try:
        with language_path.open("r", encoding="utf-8") as file:
            data = json5.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _resolve_i18n_value(value: Any, mapping: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_i18n_value(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_i18n_value(item, mapping) for item in value]
    if isinstance(value, str) and value.startswith("$"):
        translated = _lookup_i18n_text(value, mapping)
        if translated is not None:
            return translated
    return value


def _lookup_i18n_text(key: str, mapping: dict[str, Any]) -> str | None:
    normalized_key = key[1:] if key.startswith("$") else key
    if not normalized_key:
        return None

    current: Any = mapping
    for part in normalized_key.split("."):
        if not isinstance(current, dict) or part not in current:
            current = None
            break
        current = current[part]
    if isinstance(current, str):
        return current

    flat_value = mapping.get(normalized_key)
    return flat_value if isinstance(flat_value, str) else None


def _resolve_project_path(root_path: Path, raw_path: str) -> Path | None:
    candidate = Path(raw_path.replace("{PROJECT_DIR}", str(root_path)))
    if not candidate.is_absolute():
        candidate = root_path / candidate
    resolved_path = candidate.resolve()
    try:
        resolved_path.relative_to(root_path.resolve())
    except ValueError:
        return None
    return resolved_path
