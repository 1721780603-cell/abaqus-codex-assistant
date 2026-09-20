# -*- coding: utf-8 -*-
"""验证初学者完整路线和本地操作记录。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from abaqus_codex.desktop_assistant.assistant_history import (
    AssistantHistoryStore,
    HISTORY_SCHEMA,
    MAX_HISTORY_RECORDS,
    format_history,
    sanitize_history_text,
)
from abaqus_codex.desktop_assistant.beginner_guide import (
    BEGINNER_STEPS,
    format_beginner_guide,
)
from abaqus_codex.desktop_assistant.contact_guide import (
    CONTACT_SCENARIOS,
    format_contact_selection_guide,
    recommend_contact,
)


class BeginnerGuideTests(unittest.TestCase):
    """确认新手无需自行猜测后续命令。"""

    def test_catalog_contains_all_ten_ordered_steps(self):
        """完整路线必须从几何连续展示到结果报告。"""

        self.assertEqual([step[0] for step in BEGINNER_STEPS], list(range(1, 11)))
        guide = format_beginner_guide(current_step=5)
        self.assertIn("▶ 当前 第 5/10 步｜分析步", guide)
        self.assertIn("创建一个长 100 mm", guide)
        self.assertIn("最大 Mises 应力并生成中文报告", guide)
        self.assertIn("无需背诵", guide)


class ContactSelectionGuideTests(unittest.TestCase):
    """确认接触教学能区分接触、约束和连接器。"""

    def test_common_civil_scenarios_are_covered(self):
        """接触指南必须覆盖连续体、理想粘结、滑移和界面损伤。"""

        keys = {scenario.key for scenario in CONTACT_SCENARIOS}
        self.assertEqual(len(keys), len(CONTACT_SCENARIOS))
        self.assertTrue({
            "single_body",
            "perfect_bond",
            "embedded_rebar",
            "pair_contact",
            "general_contact",
            "cohesive_interface",
            "simplified_connection",
        }.issubset(keys))

    def test_recommendations_do_not_call_everything_contact(self):
        """新手必须知道 Tie、嵌入和连接器不是普通表面接触。"""

        self.assertIn("Tie", recommend_contact("perfect_bond").recommendation)
        self.assertIn(
            "Embedded Region",
            recommend_contact("embedded_rebar").recommendation,
        )
        self.assertIn(
            "Connector",
            recommend_contact("simplified_connection").recommendation,
        )

    def test_guide_teaches_decision_inputs_and_verification(self):
        """指南不仅给结论，还应要求参数来源和结果检查。"""

        guide = format_contact_selection_guide()
        self.assertIn("一分钟决策树", guide)
        self.assertIn("桩—土", guide)
        self.assertIn("摩擦系数来源", guide)
        self.assertIn("CPRESS", guide)
        self.assertIn("我确认后再生成修改计划", guide)
        self.assertIn("不会修改 Abaqus 模型", guide)

    def test_unknown_scenario_is_rejected(self):
        """未知场景不能被静默猜成某种接触。"""

        with self.assertRaises(ValueError):
            recommend_contact("guess-for-me")


class AssistantHistoryStoreTests(unittest.TestCase):
    """确认操作历史可追溯但不泄露完整路径。"""

    def test_history_survives_new_store_instance(self):
        """关闭并重新打开应用后仍能读取之前的安全摘要。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            first = AssistantHistoryStore(path)
            first.append(
                title="第 2/10 步｜修改计划",
                status="计划待确认",
                details="材料 Steel：E 从空值改为 210000 MPa",
            )
            records = AssistantHistoryStore(path).read()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "计划待确认")
            self.assertIn("210000 MPa", format_history(records))

    def test_paths_are_redacted_before_persistence(self):
        """Windows 和 POSIX 完整路径都不能写入历史。"""

        text = sanitize_history_text(
            "工作目录 C:\\private\\model.cae\n报告 /home/user/report.md"
        )
        self.assertNotIn("C:\\private", text)
        self.assertNotIn("/home/user", text)
        self.assertEqual(text.count("[本机路径已隐藏]"), 2)

    def test_corrupt_or_unknown_history_is_ignored(self):
        """历史文件损坏不能阻止助手启动。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            path.write_text("not-json", encoding="utf-8")
            self.assertEqual(AssistantHistoryStore(path).read(), [])
            path.write_text(
                json.dumps({"schema": "unknown", "records": []}),
                encoding="utf-8",
            )
            self.assertEqual(AssistantHistoryStore(path).read(), [])

    def test_history_keeps_only_bounded_recent_records(self):
        """重复使用不会让历史文件无限增长。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            store = AssistantHistoryStore(path)
            for index in range(MAX_HISTORY_RECORDS + 3):
                store.append(
                    title="记录 {0}".format(index),
                    status="检查完成",
                    details="模型没有修改。",
                )
            records = store.read()
            self.assertEqual(len(records), MAX_HISTORY_RECORDS)
            self.assertEqual(records[0]["title"], "记录 3")

    def test_history_file_uses_declared_schema(self):
        """持久化格式必须带版本，便于以后兼容升级。"""

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.json"
            AssistantHistoryStore(path).append(
                title="第 6/10 步",
                status="检查完成",
                details="无需相互作用。",
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], HISTORY_SCHEMA)


if __name__ == "__main__":
    unittest.main()
