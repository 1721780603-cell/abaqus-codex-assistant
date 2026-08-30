# -*- coding: utf-8 -*-
"""无需启动 Abaqus，验证 2021 一次性只读快照的两端协议。"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from abaqus_codex.desktop_assistant.controller import refresh_read_only
from abaqus_codex.desktop_assistant.snapshot_source import (
    MAX_SNAPSHOT_BYTES,
    SnapshotFileSource,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = PROJECT_ROOT / "abaqus_plugins" / "readonly_model_snapshot"
KERNEL_PATH = PLUGIN_DIR / "readonly_model_snapshot_kernel.py"


def load_kernel_module():
    """在没有 Abaqus 模块时加载只包含纯函数的 Kernel 源码。"""

    spec = importlib.util.spec_from_file_location(
        "readonly_model_snapshot_kernel_test", KERNEL_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_model(name="Model-1"):
    """构造只实现 repository 接口的最小假模型。"""

    model = SimpleNamespace(
        parts={"Plate": object()},
        materials={"Steel": object()},
        steps={"Initial": object(), "Step-1": object()},
        rootAssembly=SimpleNamespace(instances={"Plate-1": object()}),
        loads={"Load-1": object()},
        boundaryConditions={"Fixed": object()},
        interactions={"Contact-1": object()},
    )
    return SimpleNamespace(models={name: model})


def snapshot_payload(
    captured_at,
    *,
    pid=None,
    release="2021",
    models=None,
    random_id="a" * 32,
):
    """生成完全受控的测试快照。"""

    producer_pid = os.getpid() if pid is None else pid
    captured = datetime.fromtimestamp(captured_at, tz=timezone.utc)
    stamp = captured.strftime("%Y%m%dT%H%M%S%fZ")
    snapshot_id = "{0}_{1}_{2}".format(stamp, producer_pid, random_id)
    return {
        "schema": "abaqus-codex-readonly-snapshot",
        "schema_version": 1,
        "target_release": release,
        "complete": True,
        "snapshot_id": snapshot_id,
        "generated_at_utc": captured.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "producer_pid": producer_pid,
        "truncated": False,
        "warnings": [],
        "models": models
        if models is not None
        else [
            {
                "name": "Model-1",
                "parts": ["Plate"],
                "materials": ["Steel"],
                "steps": ["Initial", "Step-1"],
                "instances": ["Plate-1"],
                "loads": ["Load-1"],
                "boundary_conditions": ["Fixed"],
                "interactions": ["Contact-1"],
            }
        ],
    }


def write_payload(directory, payload, *, suffix=".json"):
    """按正式文件命名规则写入一份测试数据。"""

    path = Path(directory) / ("snapshot_" + payload["snapshot_id"] + suffix)
    path.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
        encoding="ascii",
    )
    return path


class AbaqusSnapshotPluginTests(unittest.TestCase):
    """确认 Abaqus 端只有固定的单次只读动作。"""

    def _runtime_modules(self, release="2021", version_error=None):
        """构造 write_readonly_snapshot 所需的两个最小运行模块。"""

        abaqus_module = ModuleType("abaqus")
        abaqus_module.mdb = sample_model()
        uti_module = ModuleType("uti")

        def get_version():
            """返回受控版本，或模拟 Abaqus 版本接口失败。"""

            if version_error is not None:
                raise version_error
            return release

        uti_module.getVersion = get_version
        return {"abaqus": abaqus_module, "uti": uti_module}

    def test_plugin_registration_is_fixed_kernel_function(self):
        """菜单必须调用无参数固定函数，不能拼接用户命令。"""

        source = (PLUGIN_DIR / "readonly_model_snapshot_plugin.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("registerKernelMenuButton", source)
        self.assertNotIn("getVersionNumbers", source)
        self.assertIn(
            'buttonText="Abaqus Codex Assistant|Refresh Read-Only Snapshot"',
            source,
        )
        self.assertIn('moduleName="readonly_model_snapshot_kernel"', source)
        self.assertIn('functionName="write_readonly_snapshot()"', source)
        self.assertIn("icon=None", source)
        self.assertNotIn('buttonText=u"', source)
        self.assertNotIn("AFXGuiCommand", source)
        self.assertNotIn("kernelInitString", source)

    def test_release_check_uses_abaqus_2021_uti_api(self):
        """Kernel 必须使用 2021 可用的 uti API，不能访问不存在的 session.about。"""

        source = KERNEL_PATH.read_text(encoding="utf-8")
        self.assertIn("uti.getVersion()", source)
        self.assertNotIn("session.about", source)
        self.assertIn("VERSION_CHECK_FAILED", source)
        self.assertIn("WRITE_FAILED", source)

    def test_plugin_sources_avoid_background_and_model_write_apis(self):
        """源码不得包含线程、网络、任意代码或模型写操作。"""

        sources = "\n".join(
            path.read_text(encoding="utf-8") for path in PLUGIN_DIR.glob("*.py")
        )
        for forbidden in (
            "threading",
            "subprocess",
            "socket",
            "urllib",
            "exec(",
            "eval(",
            "setValues(",
            "mdb.save",
            ".saveAs(",
            "Job(",
            ".submit(",
        ):
            self.assertNotIn(forbidden, sources)
        self.assertNotIn("from __future__ import annotations", sources)

    def test_collector_only_exports_limited_names(self):
        """中文和控制字符被安全处理，且结果不含路径或数值。"""

        module = load_kernel_module()
        payload = module._collect_snapshot(sample_model("模型\n一"))
        model = payload["models"][0]
        self.assertEqual(model["name"], "模型 一")
        self.assertEqual(model["materials"], ["Steel"])
        self.assertEqual(
            set(model),
            {
                "name",
                "parts",
                "materials",
                "steps",
                "instances",
                "loads",
                "boundary_conditions",
                "interactions",
            },
        )
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("working_directory", serialized)
        self.assertNotIn("elastic", serialized.lower())

    def test_writer_uses_ascii_temp_then_unique_final_json(self):
        """写入完成后只留下最终 JSON，且中文通过 ASCII 转义保存。"""

        module = load_kernel_module()
        payload = module._collect_snapshot(sample_model("中文模型"))
        with tempfile.TemporaryDirectory() as directory:
            final_path = Path(module._write_snapshot(payload, directory))
            self.assertTrue(final_path.is_file())
            self.assertEqual(final_path.suffix, ".json")
            self.assertFalse(any(Path(directory).glob("*.tmp")))
            raw = final_path.read_bytes()
            raw.decode("ascii")
            decoded = json.loads(raw.decode("ascii"))
            self.assertEqual(decoded["snapshot_id"], payload["snapshot_id"])

    def test_fixed_action_succeeds_with_abaqus_2021_runtime(self):
        """模拟 2021 Kernel 完整调用时必须生成一份快照。"""

        module = load_kernel_module()
        with tempfile.TemporaryDirectory() as directory:
            module._snapshot_directory = lambda: directory
            output = io.StringIO()
            with patch.dict(sys.modules, self._runtime_modules()), redirect_stdout(
                output
            ):
                self.assertTrue(module.write_readonly_snapshot())
            self.assertEqual(len(list(Path(directory).glob("snapshot_*.json"))), 1)
            self.assertIn("snapshot updated", output.getvalue())

    def test_fixed_action_rejects_wrong_release_without_writing(self):
        """不是 2021 时必须安全停止，且不能创建快照目录。"""

        module = load_kernel_module()
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent) / "not-created"
            module._snapshot_directory = lambda: str(directory)
            with patch.dict(sys.modules, self._runtime_modules("2022")):
                self.assertFalse(module.write_readonly_snapshot())
            self.assertFalse(directory.exists())

    def test_fixed_action_rejects_version_api_failure_without_writing(self):
        """版本接口异常时必须失败关闭，且不进入模型读取和写入。"""

        module = load_kernel_module()
        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent) / "not-created"
            module._snapshot_directory = lambda: str(directory)
            modules = self._runtime_modules(version_error=RuntimeError("boom"))
            output = io.StringIO()
            with patch.dict(sys.modules, modules), redirect_stdout(output):
                self.assertFalse(module.write_readonly_snapshot())
            self.assertFalse(directory.exists())
            self.assertIn("VERSION_CHECK_FAILED", output.getvalue())


class SnapshotFileSourceTests(unittest.TestCase):
    """确认桌面端只接受最新、完整、新鲜的 Abaqus 2021 快照。"""

    def source(self, directory, now):
        """创建不依赖真实进程状态的读取器。"""

        return SnapshotFileSource(
            directory=Path(directory),
            process_checker=lambda pid: pid == os.getpid(),
            wall_clock=lambda: now,
        )

    def test_missing_snapshot_does_not_create_directory_or_mcp_commands(self):
        """默认缺失应立即返回，不能创建目录或退回 MCP。"""

        with tempfile.TemporaryDirectory() as parent:
            directory = Path(parent) / "missing"
            status = self.source(directory, time.time()).inspect_status()
            self.assertEqual(status["status"], "missing")
            self.assertFalse(directory.exists())
            self.assertFalse((Path(parent) / "commands").exists())

    def test_fresh_snapshot_is_normalized_and_uses_export_time(self):
        """有效快照应读取白名单字段，并显示 Abaqus 导出时间。"""

        captured = 1_788_071_130
        with tempfile.TemporaryDirectory() as directory:
            write_payload(directory, snapshot_payload(captured))
            source = self.source(directory, captured + 10)
            state = refresh_read_only(source)
            self.assertEqual(state.connection_text, "快照已读取")
            self.assertIn("Abaqus 2021 手动一次性快照", state.summary_text)
            expected = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(captured))
            self.assertIn(expected, state.summary_text)
            self.assertIn("Model-1", state.summary_text)

    def test_temp_and_wrong_names_are_ignored(self):
        """半写临时文件和非协议文件不能被当成快照。"""

        now = time.time()
        with tempfile.TemporaryDirectory() as directory:
            payload = snapshot_payload(now)
            write_payload(directory, payload, suffix=".tmp")
            (Path(directory) / "latest.json").write_text("{}", encoding="utf-8")
            status = self.source(directory, now).inspect_status()
            self.assertEqual(status["status"], "missing")

    def test_newest_invalid_snapshot_does_not_fall_back_to_old(self):
        """最新文件损坏时必须失败关闭，不能悄悄展示旧模型。"""

        now = 1_788_071_130
        with tempfile.TemporaryDirectory() as directory:
            write_payload(directory, snapshot_payload(now - 10, random_id="a" * 32))
            newest = snapshot_payload(now, random_id="b" * 32)
            newest_path = write_payload(directory, newest)
            newest_path.write_bytes(b"{broken")
            status = self.source(directory, now + 1).inspect_status()
            self.assertEqual(status["status"], "invalid")

    def test_two_snapshots_in_one_second_choose_later_microsecond(self):
        """同一秒快速刷新两次时，必须选择真正后生成的模型。"""

        base = 1_788_071_130
        old_models = snapshot_payload(base + 0.1)["models"]
        new_models = snapshot_payload(base + 0.9)["models"]
        old_models[0]["name"] = "Old-Model"
        new_models[0]["name"] = "New-Model"
        with tempfile.TemporaryDirectory() as directory:
            write_payload(
                directory,
                snapshot_payload(base + 0.1, models=old_models, random_id="a" * 32),
            )
            write_payload(
                directory,
                snapshot_payload(base + 0.9, models=new_models, random_id="b" * 32),
            )
            data = self.source(directory, base + 1).get_model_info()
            self.assertEqual(data["models"][0]["name"], "New-Model")

    def test_stale_future_dead_and_wrong_release_are_rejected(self):
        """时间、进程或版本任一不正确都不能显示为当前模型。"""

        now = 1_788_071_130
        cases = (
            (snapshot_payload(now - 301), "stale", None),
            (snapshot_payload(now + 31), "future", None),
            (snapshot_payload(now, pid=987654321), "dead-process", None),
            (snapshot_payload(now, pid=0x100000000), "invalid", None),
            (snapshot_payload(now, release="2022"), "invalid", None),
        )
        for index, (payload, expected, _) in enumerate(cases):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                payload["snapshot_id"] = payload["snapshot_id"][:-32] + format(index + 1, "032x")
                write_payload(directory, payload)
                status = self.source(directory, now).inspect_status()
                self.assertEqual(status["status"], expected)

    def test_oversized_and_path_bearing_invalid_data_do_not_leak(self):
        """危险数据只产生安全状态，不把私人路径带进界面。"""

        now = 1_788_071_130
        with tempfile.TemporaryDirectory() as directory:
            payload = snapshot_payload(now)
            path = write_payload(directory, payload)
            path.write_bytes(b"x" * (MAX_SNAPSHOT_BYTES + 1))
            state = refresh_read_only(self.source(directory, now))
            self.assertEqual(state.tone, "offline")
            self.assertNotIn("Users", state.summary_text)

        with tempfile.TemporaryDirectory() as directory:
            payload = snapshot_payload(now)
            payload["private_path"] = r"C:\Users\Alice\secret.cae"
            write_payload(directory, payload)
            state = refresh_read_only(self.source(directory, now))
            self.assertNotIn("Alice", state.summary_text)
            self.assertNotIn("secret.cae", state.log_text)

        with tempfile.TemporaryDirectory() as directory:
            payload = snapshot_payload(now)
            payload["models"][0]["name"] = (
                r"Plate from C:\Users\Alice\secret.cae"
            )
            write_payload(directory, payload)
            state = refresh_read_only(self.source(directory, now))
            self.assertNotIn("Alice", state.summary_text)
            self.assertNotIn("secret.cae", state.log_text)


if __name__ == "__main__":
    unittest.main()
