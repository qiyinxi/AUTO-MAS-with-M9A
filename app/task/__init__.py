#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


__all__ = [
    "MaaManager",
    "SrcManager",
    "M9AManager",
    "MaaFWManager",
    "GeneralManager",
    "MaaEndManager",
    "OkwwManager",
    "HSRManager",
]


def __getattr__(name: str):
    if name == "MaaManager":
        from .MAA import MaaManager

        return MaaManager
    if name == "SrcManager":
        from .SRC import SrcManager

        return SrcManager
    if name == "M9AManager":
        from .M9A import M9AManager

        return M9AManager
    if name == "MaaFWManager":
        from .MaaFW import MaaFWManager

        return MaaFWManager
    if name == "GeneralManager":
        from .general import GeneralManager

        return GeneralManager
    if name == "MaaEndManager":
        from .MaaEnd import MaaEndManager

        return MaaEndManager
    if name == "OkwwManager":
        from .Okww import OkwwManager

        return OkwwManager
    if name == "HSRManager":
        from .HSR import HSRManager

        return HSRManager
    raise AttributeError(name)
