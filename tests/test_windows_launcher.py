# -*- coding: utf-8 -*-
"""验证 Windows 一键启动文件不会再次出现编码故障。"""

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = PROJECT_ROOT / "启动中文建模助手.cmd"


class WindowsLauncherTests(unittest.TestCase):
    """检查会直接影响 cmd.exe 解析稳定性的约束。"""

    def test_launcher_uses_ascii_only(self):
        """启动脚本必须兼容 GBK 和 UTF-8 等不同系统代码页。"""

        content = LAUNCHER_PATH.read_bytes()
        self.assertTrue(content)
        self.assertTrue(all(byte < 128 for byte in content))

    def test_launcher_uses_windows_line_endings(self):
        """批处理脚本必须使用 Windows CRLF 换行。"""

        content = LAUNCHER_PATH.read_bytes()
        self.assertIn(b"\r\n", content)
        self.assertNotIn(b"\n", content.replace(b"\r\n", b""))

    def test_launcher_uses_project_python(self):
        """启动器不得静默退回系统中的未知 Python。"""

        content = LAUNCHER_PATH.read_text(encoding="ascii")
        self.assertIn(r".venv\Scripts\python.exe", content)
        self.assertIn("-m abaqus_codex assistant", content)


if __name__ == "__main__":
    unittest.main()
