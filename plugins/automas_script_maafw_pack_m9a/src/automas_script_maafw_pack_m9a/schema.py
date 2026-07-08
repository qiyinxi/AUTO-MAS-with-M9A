"""M9A 专项包配置 schema。

与 MaaFW 共用同一套配置结构，仅覆盖默认脚本名称和路径标签。
"""

from __future__ import annotations

from dataclasses import replace

from automas_script_maafw.schema import SCRIPT_GROUPS, USER_GROUPS, build_source_config
from app.plugins.fields import PluginField, PluginFieldDeclaration, PluginFieldGroup

# 覆盖 Info 分组的第一个字段（Name）的默认值
_info_group = SCRIPT_GROUPS[0]
_m9a_name_field = replace(_info_group.fields[0], default="新 M9A 脚本")
_m9a_path_field = replace(
    _info_group.fields[2],
    label="M9A 项目路径",
    placeholder="选择包含 interface.json 的 M9A 项目目录",
)
_m9a_info_fields = (
    _m9a_name_field,
    _info_group.fields[1],
    _m9a_path_field,
    *_info_group.fields[3:],
)

M9A_SCRIPT_GROUPS: tuple[PluginFieldGroup, ...] = (
    replace(_info_group, fields=_m9a_info_fields),
    *SCRIPT_GROUPS[1:],
)

# 用户配置与 MaaFW 完全一致
M9A_USER_GROUPS = USER_GROUPS

__all__ = ["M9A_SCRIPT_GROUPS", "M9A_USER_GROUPS", "build_source_config"]
