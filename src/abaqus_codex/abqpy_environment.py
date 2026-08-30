# -*- coding: utf-8 -*-
"""检测当前 Python 环境中的 abqpy，并判断其是否匹配 Abaqus。"""

from __future__ import annotations

import re
import sys
from importlib import metadata
from typing import Dict, Optional

from abaqus_codex.paths import project_python_executable


# Abaqus 和 abqpy 的新版版本号都以四位年份开头，例如 2021 和 2021.7.3。
RELEASE_YEAR_PATTERN = re.compile(r"^(20\d{2})(?:\.|$)")

# 只有完成维护者真机建模、求解、ODB 读取和报告验证的年份才能列在这里。
VERIFIED_ABAQUS_YEARS = frozenset({2021})

# 用户实测已经确认存在兼容问题的年份保留检测，但禁止自动安装和运行。
KNOWN_INCOMPATIBLE_ABAQUS_YEARS = frozenset({2026})

# 自动安装和启动采用白名单；未来年份即使能解析，也必须先经过项目评估。
AUTOMATION_ALLOWED_ABAQUS_YEARS = frozenset({2021, 2022, 2023, 2024, 2025})


def parse_release_year(version: Optional[str]) -> Optional[int]:
    """从 Abaqus 或 abqpy 版本号中读取四位年份。"""

    if not version:
        return None

    match = RELEASE_YEAR_PATTERN.match(version.strip())
    if match is None:
        return None
    return int(match.group(1))


def abqpy_matches_abaqus(
    abaqus_version: Optional[str], abqpy_version: Optional[str]
) -> Optional[bool]:
    """比较两个版本的年份；无法识别时返回空值，避免错误猜测。"""

    abaqus_year = parse_release_year(abaqus_version)
    abqpy_year = parse_release_year(abqpy_version)
    if abaqus_year is None or abqpy_year is None:
        return None
    return abaqus_year == abqpy_year


def recommended_abqpy_requirement(
    abaqus_version: Optional[str],
) -> Optional[str]:
    """为允许使用的 Abaqus 年份生成 abqpy 规格；已知不兼容时返回空值。"""

    abaqus_year = parse_release_year(abaqus_version)
    if abaqus_year not in AUTOMATION_ALLOWED_ABAQUS_YEARS:
        return None
    return "abqpy=={0}.*".format(abaqus_year)


def is_known_incompatible(abaqus_version: Optional[str]) -> bool:
    """判断该 Abaqus 年份是否已被项目明确列为不兼容。"""

    return parse_release_year(abaqus_version) in KNOWN_INCOMPATIBLE_ABAQUS_YEARS


def is_automation_allowed(abaqus_version: Optional[str]) -> bool:
    """只有项目明确列出的年份才允许自动安装、连接或求解。"""

    return parse_release_year(abaqus_version) in AUTOMATION_ALLOWED_ABAQUS_YEARS


def abaqus_verification_level(abaqus_version: Optional[str]) -> str:
    """区分维护者已验证版本、候选版本和无法识别的旧版本。"""

    abaqus_year = parse_release_year(abaqus_version)
    if abaqus_year is None:
        return "unknown"
    if abaqus_year in KNOWN_INCOMPATIBLE_ABAQUS_YEARS:
        return "known_incompatible"
    if abaqus_year in VERIFIED_ABAQUS_YEARS:
        return "maintainer_verified"
    if abaqus_year in AUTOMATION_ALLOWED_ABAQUS_YEARS:
        return "detected_unverified"
    return "detected_unsupported"


def installed_abqpy_version() -> Optional[str]:
    """读取当前 Python 环境里已安装的 abqpy 版本。"""

    try:
        return metadata.version("abqpy")
    except metadata.PackageNotFoundError:
        return None


def inspect_abqpy(abaqus_version: Optional[str]) -> Dict[str, object]:
    """汇总 abqpy 的安装、版本兼容和当前 Python 信息。"""

    version = installed_abqpy_version()
    installed = version is not None
    compatible = abqpy_matches_abaqus(abaqus_version, version)
    verification_level = abaqus_verification_level(abaqus_version)
    usable = (
        installed
        and compatible is True
        and verification_level
        in ("maintainer_verified", "detected_unverified")
    )

    if verification_level == "known_incompatible":
        message = (
            "检测到已知不兼容的 Abaqus 年份，当前项目已停止自动安装和运行。"
        )
    elif verification_level == "detected_unsupported":
        message = "检测到尚未列入自动流程的 Abaqus 年份，需要项目先评估。"
    elif not installed:
        message = "当前 Python 环境中没有安装 abqpy。"
    elif compatible is True:
        message = "abqpy 已安装，并且与 Abaqus 版本匹配。"
    elif compatible is False:
        message = "abqpy 已安装，但与 Abaqus 年份不匹配。"
    else:
        message = "abqpy 已安装，但暂时无法判断版本是否匹配。"

    return {
        "installed": installed,
        "usable": usable,
        "version": version,
        "abaqus_version": abaqus_version,
        "compatible": compatible,
        "recommended_requirement": recommended_abqpy_requirement(
            abaqus_version
        ),
        "abaqus_verification_level": verification_level,
        "python_executable": str(project_python_executable()),
        "message": message,
    }


def main() -> int:
    """检测 Abaqus 和 abqpy，并显示适合初学者阅读的结果。"""

    # 延后导入可以避免纯版本解析测试启动任何 Abaqus 命令。
    from abaqus_codex.environment import inspect_abaqus

    abaqus_result = inspect_abaqus()
    result = inspect_abqpy(abaqus_result["version"])

    print("abqpy 环境检测")
    print("----------------")
    print("检测结果：{0}".format(result["message"]))
    print("当前 Python：{0}".format(result["python_executable"]))

    if result["abaqus_version"]:
        print("Abaqus 版本：{0}".format(result["abaqus_version"]))
    if result["version"]:
        print("abqpy 版本：{0}".format(result["version"]))

    # 只有安装成功且年份匹配时，环境检测才算通过。
    return 0 if result["usable"] else 1


if __name__ == "__main__":
    sys.exit(main())
