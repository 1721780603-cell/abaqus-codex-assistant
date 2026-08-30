# -*- coding: utf-8 -*-
"""无需启动 Abaqus，检查 2021 中文助手插件窗口外壳。"""

import importlib.util
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = PROJECT_ROOT / "abaqus_plugins" / "ai_modeling_assistant"


def read_plugin_source(name):
    """读取 UTF-8 插件源码。"""

    return (PLUGIN_DIR / name).read_text(encoding="utf-8")


class Abaqus2021PluginShellTests(unittest.TestCase):
    """确认界面可注册，同时没有真实模型写入口。"""

    def test_plugin_sources_compile_as_python2_compatible_subset(self):
        """源码不使用 f-string、类型注解等 Python 3 专用语法。"""

        for path in sorted(PLUGIN_DIR.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
            self.assertNotIn("from __future__ import annotations", source)

    def test_menu_registration_is_limited_to_abaqus_2021_shell(self):
        """注册文件应提供清晰菜单名称，且不初始化 Kernel 命令。"""

        source = read_plugin_source("ai_modeling_assistant_plugin.py")
        self.assertIn("registerGuiMenuButton", source)
        self.assertIn("AI 中文建模助手", source)
        self.assertIn('version="0.2.2"', source)
        self.assertNotIn("kernelInitString", source)
        self.assertNotIn("AFXGuiCommand", source)

    def test_dialog_has_required_sections_and_disabled_apply(self):
        """窗口包含首版区域，并从代码层禁用应用按钮。"""

        source = read_plugin_source("ai_modeling_assistant_dialog.py")
        for label in (
            "中文命令",
            "模型摘要（模拟数据）",
            "修改计划（仅预览）",
            "执行日志",
            "清空",
            "应用修改（尚未启用）",
        ):
            self.assertIn(label, source)
        self.assertIn("self.apply_button.disable()", source)
        self.assertIn("AFXDataDialog.show(self)", source)

    def test_dialog_contains_no_model_network_or_arbitrary_code_entry(self):
        """界面演示不能读取模型、联网或执行任意命令。"""

        sources = "\n".join(
            path.read_text(encoding="utf-8") for path in PLUGIN_DIR.glob("*.py")
        )
        for forbidden in (
            "sendCommand(",
            "AFXGuiCommand(",
            "execute_script",
            "exec(",
            "eval(",
            "subprocess",
            "urllib",
            "socket",
            "from kernelAccess import mdb",
        ):
            self.assertNotIn(forbidden, sources)

    def test_mock_preview_is_safe_and_does_not_log_command(self):
        """模拟层只显示有限文本，日志不复制用户可能输入的敏感内容。"""

        module_path = PLUGIN_DIR / "mock_preview.py"
        spec = importlib.util.spec_from_file_location("mock_preview_test", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        command = "修改材料\n" + "x" * 1000
        normalized = module.normalize_command(command)
        self.assertNotIn("\n", normalized)
        self.assertLessEqual(len(normalized), module.MAX_COMMAND_LENGTH)
        self.assertIn("模拟计划，不会执行", module.build_mock_plan(command))
        self.assertNotIn("修改材料", module.build_mock_log())


if __name__ == "__main__":
    unittest.main()
