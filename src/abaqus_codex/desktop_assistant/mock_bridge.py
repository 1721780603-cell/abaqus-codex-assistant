# -*- coding: utf-8 -*-
"""没有 Abaqus 时用于教学和界面检查的显式模拟桥接。"""

from __future__ import annotations

import copy
from typing import Dict, Mapping

from abaqus_codex.assistant_protocol import validate_action_plan
from abaqus_codex.desktop_assistant.material_flow import (
    MaterialCommandError,
    MaterialElasticState,
    compute_material_fingerprint,
)


MOCK_MODEL_INFO = {
    "models": [
        {
            "name": "Model-1",
            "parts": ["Plate（模拟）"],
            "materials": ["Steel"],
            "steps": ["Initial", "TensionStep（模拟）"],
            "assemblies": ["Plate-1（模拟）"],
            "loads": ["RightEdgeLoad（模拟）"],
            "bcs": ["LeftFixed（模拟）"],
            "interactions": [],
        }
    ],
    "current_viewport": "Viewport: 1（模拟）",
    # 这个字段用于测试裁剪逻辑，界面不得显示它。
    "working_directory": "C:/private/example",
}


class MockReadOnlyBridge:
    """返回确定性数据；必须通过 --mock 明确启用。"""

    is_mock = True
    source_kind = "mock"
    mode_name = "显式模拟"

    def __init__(self) -> None:
        """保存仅存在于本次模拟进程中的材料值。"""

        self.youngs_modulus = 200000.0
        self.poisson_ratio = 0.3
        self.apply_count = 0

    def inspect_status(self) -> Dict[str, object]:
        """模拟模式始终可用，但不会声称连接了 Abaqus。"""

        return {
            "responsive": True,
            "status": "mock",
            "pid": None,
            "message": "当前为显式模拟模式。",
        }

    def ping(self, timeout_seconds: float = 2.0) -> Dict[str, object]:
        """返回模拟 pong，方便以后统一体检接口。"""

        return {"response": "mock-pong", "version": "mock"}

    def get_model_info(self, timeout_seconds: float = 5.0) -> Dict[str, object]:
        """复制返回值，避免测试或界面意外修改共享常量。"""

        return copy.deepcopy(MOCK_MODEL_INFO)

    def inspect_material_elastic(
        self,
        model_name: str,
        material_name: str,
        *,
        timeout_seconds: float = 5.0,
    ) -> MaterialElasticState:
        """返回确定性的模拟旧值，不访问 Abaqus 或磁盘。"""

        if model_name != "Model-1" or material_name != "Steel":
            raise MaterialCommandError("模拟模型中没有指定的模型或材料。")
        return MaterialElasticState(
            model_name=model_name,
            material_name=material_name,
            youngs_modulus=self.youngs_modulus,
            poisson_ratio=self.poisson_ratio,
            stress_unit="MPa",
            fingerprint=compute_material_fingerprint(
                model_name,
                material_name,
                self.youngs_modulus,
                self.poisson_ratio,
            ),
        )

    def apply_material_plan(
        self,
        plan: Mapping[str, object],
        *,
        timeout_seconds: float = 30.0,
    ) -> Dict[str, object]:
        """模拟应用一次计划；明确不创建真实 CAE 文件。"""

        checked = validate_action_plan(plan)
        action = checked["actions"][0]
        current = self.inspect_material_elastic(
            checked["model_name"], action["target"]["material"]
        )
        if current.fingerprint != checked["model_fingerprint"]:
            raise MaterialCommandError("模拟材料旧值已经变化，请重新生成计划。")
        expected_before = action["before"]
        if (
            expected_before["youngs_modulus"] != self.youngs_modulus
            or expected_before["poisson_ratio"] != self.poisson_ratio
        ):
            raise MaterialCommandError("模拟材料旧值已经变化，请重新生成计划。")

        before = dict(expected_before)
        after = dict(action["after"])
        self.youngs_modulus = float(after["youngs_modulus"])
        self.poisson_ratio = float(after["poisson_ratio"])
        self.apply_count += 1
        return {
            "plan_id": checked["plan_id"],
            "action_id": action["id"],
            "model": checked["model_name"],
            "material": action["target"]["material"],
            "before": before,
            "after": after,
            "working_copy_name": "mock_model__aca_edit_{0}.cae".format(
                self.apply_count
            ),
            "same_directory": True,
            "original_untouched": True,
        }


__all__ = ["MOCK_MODEL_INFO", "MockReadOnlyBridge"]
