# -*- coding: utf-8 -*-
"""确认五个 Abaqus 端脚本的 JSON 辅助函数可在 Python 3 下运行。"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


SCRIPT_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "abaqus_codex"
    / "abaqus_scripts"
)
SCRIPT_NAMES = (
    "rectangle_tension.py",
    "plate_with_hole_tension.py",
    "cantilever_bending.py",
    "biaxial_tension.py",
    "moving_load_road.py",
)


def _fake_abaqus_modules(script_path: Path):
    """根据脚本导入项创建最小假模块，导入时绝不启动 Abaqus。"""

    # 常量只在真正建模时使用；本测试只调用 JSON 函数，因此用名称占位即可。
    source = script_path.read_text(encoding="utf-8")
    constants = types.ModuleType("abaqusConstants")
    inside_constants = False
    for line in source.splitlines():
        if line.startswith("from abaqusConstants import ("):
            inside_constants = True
            continue
        if inside_constants and line.strip() == ")":
            break
        if inside_constants:
            name = line.strip().rstrip(",")
            if name:
                setattr(constants, name, name)

    abaqus = types.ModuleType("abaqus")
    abaqus.mdb = Mock(name="mdb")
    cae_modules = types.ModuleType("caeModules")
    cae_modules.__all__ = []
    odb_access = types.ModuleType("odbAccess")
    odb_access.openOdb = Mock(name="openOdb")

    return {
        "abaqus": abaqus,
        "abaqusConstants": constants,
        "caeModules": cae_modules,
        "odbAccess": odb_access,
        "mesh": types.ModuleType("mesh"),
        "regionToolset": types.ModuleType("regionToolset"),
    }


def _load_script(script_name: str):
    """以普通 Python 3 模块加载脚本，同时隔离 Abaqus 专用模块。"""

    script_path = SCRIPT_DIRECTORY / script_name
    module_name = "_python3_compat_{0}".format(script_path.stem)
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法创建脚本导入规格：{0}".format(script_path))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, _fake_abaqus_modules(script_path)):
        spec.loader.exec_module(module)
    return module


class AbaqusScriptPython3CompatibilityTests(unittest.TestCase):
    """逐一验证所有内置模型，不允许只修复其中一个示例。"""

    def test_byteify_keeps_python3_text_and_nested_data(self):
        """Python 3 字符串必须保持 str，不能引用不存在的 unicode 或转成 bytes。"""

        payload = {
            "标题": "圆孔板拉伸",
            "列表": ["中文", {"版本": "2026"}],
        }

        for script_name in SCRIPT_NAMES:
            with self.subTest(script=script_name):
                module = _load_script(script_name)
                converted = module._byteify(payload)
                self.assertEqual(converted, payload)
                self.assertIsInstance(converted["标题"], str)
                self.assertIsInstance(converted["列表"][0], str)

    def test_write_result_produces_utf8_json_in_python3(self):
        """结果文件应为有效 UTF-8 JSON，并完整保留中文与换行。"""

        payload = {
            "模型": "二维矩形板",
            "maximum_displacement": 0.125,
            "maximum_mises_stress": 245.5,
        }

        for script_name in SCRIPT_NAMES:
            with self.subTest(script=script_name):
                module = _load_script(script_name)
                with tempfile.TemporaryDirectory() as directory:
                    result_path = Path(directory) / "结果.json"
                    module._write_result(str(result_path), payload)
                    raw = result_path.read_bytes()

                self.assertTrue(raw.endswith(b"\n"))
                self.assertIn("二维矩形板".encode("utf-8"), raw)
                self.assertEqual(json.loads(raw.decode("utf-8")), payload)

    def test_load_config_reads_utf8_json_in_python3(self):
        """配置读取应保留中文和 Python 3 文本类型。"""

        payload = {"模型": {"名称": "高速公路动荷载"}, "网格": 25.0}

        for script_name in SCRIPT_NAMES:
            with self.subTest(script=script_name):
                module = _load_script(script_name)
                with tempfile.TemporaryDirectory() as directory:
                    config_path = Path(directory) / "配置.json"
                    config_path.write_text(
                        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                    )
                    loaded = module._load_config(str(config_path))

                self.assertEqual(loaded, payload)
                self.assertIsInstance(loaded["模型"]["名称"], str)


if __name__ == "__main__":
    unittest.main()
