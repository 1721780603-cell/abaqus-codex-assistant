# -*- coding: utf-8 -*-
"""管理用户场景选择，不根据学历推断论文访问权限。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from abaqus_codex.configuration import ConfigurationError, write_json


SCENARIOS = {
    "learning": "Abaqus 入门学习",
    "paper": "单篇论文复现",
    "research": "科研参数分析",
    "production": "实际工程项目",
    "teaching": "课程与教学演示",
}


def build_profile(scenario: str) -> Dict[str, object]:
    """根据场景生成最小用户配置，不记录身份和论文账号。"""

    if scenario not in SCENARIOS:
        raise ConfigurationError("未知使用场景：{0}".format(scenario))

    return {
        "scenario": scenario,
        "scenario_name": SCENARIOS[scenario],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "paper_access_notice": (
            "仅使用开放获取论文或用户本人合法获得的文献；"
            "程序不保存机构密码、Cookie、验证码或会话令牌。"
        ),
    }


def save_profile(path: Path, scenario: str) -> Dict[str, object]:
    """保存场景配置并返回写入内容。"""

    profile = build_profile(scenario)
    write_json(path, profile)
    return profile


def prompt_scenario() -> str:
    """用简单编号让初学者选择场景。"""

    keys = list(SCENARIOS)
    print("请选择使用场景：")
    for index, key in enumerate(keys, start=1):
        print("{0}. {1}".format(index, SCENARIOS[key]))

    choice = input("请输入编号：").strip()
    if not choice.isdigit() or not 1 <= int(choice) <= len(keys):
        raise ConfigurationError("场景编号无效。")
    return keys[int(choice) - 1]
