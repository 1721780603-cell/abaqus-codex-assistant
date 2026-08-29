# -*- coding: utf-8 -*-
"""测试 Abaqus 环境检测中的纯文本解析功能。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from abaqus_codex.abqpy_environment import (
    abqpy_matches_abaqus,
    parse_release_year,
)
from abaqus_codex.environment import (
    parse_abaqus_python_info,
    parse_abaqus_version,
)
from abaqus_codex.mcp_environment import (
    parse_abaqus_mcp_names,
    vendor_python_paths,
)
from abaqus_codex.mcp_setup import McpSetupError, setup_mcp


class AbaqusVersionParseTests(unittest.TestCase):
    """确认不同格式的 Abaqus 版本号都能正确识别。"""

    def test_parse_year_version(self) -> None:
        """应当识别 Abaqus 2021 形式的版本号。"""

        output = "Abaqus JOB abaqus\nAbaqus 2021\nAbaqus JOB abaqus COMPLETED"
        self.assertEqual(parse_abaqus_version(output), "2021")

    def test_parse_legacy_version(self) -> None:
        """应当识别 Abaqus 6.14-5 形式的旧版本号。"""

        output = "Abaqus 6.14-5"
        self.assertEqual(parse_abaqus_version(output), "6.14-5")

    def test_missing_version(self) -> None:
        """没有版本号时应返回空值，而不是猜测版本。"""

        output = "没有可识别的 Abaqus 版本信息"
        self.assertIsNone(parse_abaqus_version(output))


class AbaqusPythonParseTests(unittest.TestCase):
    """确认 Abaqus Python 信息能够从复杂启动输出中准确提取。"""

    def test_parse_python_info(self) -> None:
        """应当同时识别 Python 版本和可执行文件路径。"""

        output = (
            "Abaqus 启动信息\n"
            "ABAQUS_PYTHON_VERSION=2.7.15\n"
            "ABAQUS_PYTHON_EXECUTABLE=C:\\Abaqus\\SMAPython.exe\n"
        )
        version, executable = parse_abaqus_python_info(output)

        self.assertEqual(version, "2.7.15")
        self.assertEqual(executable, r"C:\Abaqus\SMAPython.exe")

    def test_missing_python_info(self) -> None:
        """没有固定标记时不应猜测 Python 信息。"""

        version, executable = parse_abaqus_python_info("Python 信息缺失")

        self.assertIsNone(version)
        self.assertIsNone(executable)


class AbaqusMcpListParseTests(unittest.TestCase):
    """确认 Codex MCP 列表能够安全识别 Abaqus 服务器名称。"""

    def test_parse_registered_abaqus_server(self) -> None:
        """列表中存在 Abaqus MCP 时应返回其名称。"""

        output = (
            "Name               Command  Status\n"
            "abaqus-mcp-server  python   enabled\n"
            "another-server     node     enabled\n"
        )
        self.assertEqual(parse_abaqus_mcp_names(output), ["abaqus-mcp-server"])

    def test_parse_empty_server_list(self) -> None:
        """没有配置 MCP 时应返回空列表。"""

        output = "No MCP servers configured yet."
        self.assertEqual(parse_abaqus_mcp_names(output), [])


class AbaqusMcpVendorPathTests(unittest.TestCase):
    """确认 MCP 可选依赖目录受限时，环境体检仍能继续。"""

    def test_unreadable_optional_directory_is_skipped(self) -> None:
        """无权读取单个 pywin32 子目录时不应中断整个首次向导。"""

        with tempfile.TemporaryDirectory() as directory:
            vendor_path = Path(directory) / "vendor"
            win32_path = vendor_path / "win32"
            win32_path.mkdir(parents=True)
            blocked_path = win32_path / "lib"
            original_is_dir = Path.is_dir

            def guarded_is_dir(path: Path) -> bool:
                """模拟沙箱只拒绝一个可选子目录。"""

                if path == blocked_path:
                    raise PermissionError("测试用拒绝访问")
                return original_is_dir(path)

            with patch.object(Path, "is_dir", guarded_is_dir):
                paths = vendor_python_paths(vendor_path)

        self.assertIn(vendor_path, paths)
        self.assertIn(win32_path, paths)
        self.assertNotIn(blocked_path, paths)


class AbqpyVersionTests(unittest.TestCase):
    """确认 abqpy 与 Abaqus 的年份兼容判断准确。"""

    def test_parse_abqpy_release_year(self) -> None:
        """应当从 abqpy 2021.7.3 中读取年份 2021。"""

        self.assertEqual(parse_release_year("2021.7.3"), 2021)

    def test_matching_release_years(self) -> None:
        """Abaqus 2021 应当与 abqpy 2021 系列匹配。"""

        self.assertTrue(abqpy_matches_abaqus("2021", "2021.7.3"))

    def test_mismatching_release_years(self) -> None:
        """Abaqus 2021 不应当与 abqpy 2022 系列匹配。"""

        self.assertFalse(abqpy_matches_abaqus("2021", "2022.7.3"))

    def test_unknown_legacy_release(self) -> None:
        """旧式 Abaqus 版本无法比较时应返回空值。"""

        self.assertIsNone(abqpy_matches_abaqus("6.14-5", "2021.7.3"))


class McpSetupConsentTests(unittest.TestCase):
    """确认 MCP 安装必须由用户明确授权。"""

    def test_setup_without_confirmation_is_rejected(self) -> None:
        """没有 --yes 时不应下载或修改任何用户文件。"""

        with self.assertRaises(McpSetupError):
            setup_mcp(confirmed=False)


if __name__ == "__main__":
    unittest.main()
