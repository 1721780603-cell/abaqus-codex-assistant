# -*- coding: utf-8 -*-
"""验证旧 MCP 自动启动修复只改已知代码且完整备份。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from abaqus_codex.legacy_mcp_startup import (
    AUTO_START_BLOCK,
    LegacyMcpStartupError,
    disable_legacy_mcp_autostart,
)


class LegacyMcpStartupTests(unittest.TestCase):
    """确认修复器不扩大修改范围。"""

    def test_confirmation_is_required(self):
        """没有明确确认时连文件都不读取。"""

        with self.assertRaisesRegex(LegacyMcpStartupError, "明确确认"):
            disable_legacy_mcp_autostart(Path("missing.env"), confirmed=False)

    def test_known_block_is_backed_up_and_disabled(self):
        """只替换自动启动块，其他内容保持不变。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "abaqus_v6.env"
            original = "# header\n" + AUTO_START_BLOCK + "# footer\n"
            path.write_text(original, encoding="utf-8")
            result = disable_legacy_mcp_autostart(path, confirmed=True)
            backup = Path(str(result["backup"]))
            self.assertEqual(backup.read_text(encoding="utf-8"), original)
            updated = path.read_text(encoding="utf-8")
            self.assertNotIn("__main__.__dict__['mcp_start']()", updated)
            self.assertIn("legacy MCP auto-start is disabled", updated)
            # Abaqus Python 2.7 在无编码声明的 .env 中只接受 ASCII。
            path.read_bytes().decode("ascii")
            self.assertIn("# header", updated)
            self.assertIn("# footer", updated)

    def test_unknown_file_is_not_changed(self):
        """用户自定义环境文件不符合已知结构时必须停止。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "abaqus_v6.env"
            path.write_text("# user config\n", encoding="utf-8")
            with self.assertRaisesRegex(LegacyMcpStartupError, "没有找到"):
                disable_legacy_mcp_autostart(path, confirmed=True)
            self.assertEqual(path.read_text(encoding="utf-8"), "# user config\n")


if __name__ == "__main__":
    unittest.main()
