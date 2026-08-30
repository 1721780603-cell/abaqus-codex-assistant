# -*- coding: utf-8 -*-
"""不用 Abaqus，验证 2021 安全材料执行器的白名单和保存顺序。"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from abaqus_codex.desktop_assistant.material_flow import (
    MaterialElasticState,
    build_material_plan,
    compute_material_fingerprint,
    parse_material_command,
)
from abaqus_codex.desktop_assistant.rectangle_flow import (
    build_rectangle_plan,
    parse_rectangle_command,
)


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / "abaqus_plugins" / "safe_material_action"
KERNEL_PATH = PLUGIN_ROOT / "safe_material_action_kernel.py"
GUI_PATH = PLUGIN_ROOT / "safe_material_action_plugin.py"


def _load_kernel():
    """按独立模块名加载执行器，避免测试间共享全局状态。"""

    specification = importlib.util.spec_from_file_location(
        "safe_material_action_kernel_test", KERNEL_PATH
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class FakeElastic:
    """记录 Abaqus Elastic.setValues 调用的最小替身。"""

    def __init__(self, events):
        self.table = ((200000.0, 0.3),)
        self.type = "ISOTROPIC"
        self.temperatureDependency = False
        self.dependencies = 0
        self.events = events

    def setValues(self, table):
        """记录新表并模拟 Abaqus 更新对象。"""

        self.events.append(("setValues", table))
        self.table = table


class FakeMdb:
    """记录另存和保存顺序的最小 MDB。"""

    def __init__(self, original, elastic, events):
        self.pathName = str(original)
        self.events = events
        material = SimpleNamespace(elastic=elastic)
        model = SimpleNamespace(materials={"Steel": material})
        self.models = {"Model-1": model}

    def save(self):
        """记录修改后的工作副本保存。"""

        self.events.append(("save", self.pathName))


class FakeAbaqus:
    """模拟先打开已复制的 CAE 工作副本。"""

    def __init__(self, mdb, events):
        self.mdb = mdb
        self.events = events

    def openMdb(self, pathName):
        """记录打开副本，并让后续保存只指向副本。"""

        self.events.append(("openMdb", pathName))
        self.mdb.pathName = pathName
        return self.mdb


class FakeSketch:
    """记录固定矩形草图的两个角点。"""

    def __init__(self, events):
        self.events = events

    def rectangle(self, point1, point2):
        """模拟 Abaqus 草图矩形 API。"""

        self.events.append(("rectangle", point1, point2))


class FakePart:
    """记录二维零件由草图生成壳面的动作。"""

    def __init__(self, events):
        self.events = events

    def BaseShell(self, sketch):
        """模拟二维 BaseShell 创建。"""

        self.events.append(("BaseShell", sketch))


class FakeGeometryModel:
    """提供矩形动作所需的最小 Model API。"""

    def __init__(self, events):
        self.events = events
        self.parts = {}
        self.sketches = {}

    def ConstrainedSketch(self, name, sheetSize):
        """建立并登记临时草图。"""

        sketch = FakeSketch(self.events)
        self.sketches[name] = sketch
        self.events.append(("ConstrainedSketch", name, sheetSize))
        return sketch

    def Part(self, name, dimensionality, type):
        """建立并登记固定二维可变形零件。"""

        part = FakePart(self.events)
        self.parts[name] = part
        self.events.append(("Part", name, dimensionality, type))
        return part


class FakeGeometryMdb:
    """模拟包含现有 Model-1 的矩形工作数据库。"""

    def __init__(self, original, events):
        self.pathName = str(original)
        self.events = events
        self.models = {"Model-1": FakeGeometryModel(events)}

    def Model(self, name):
        """允许计划在缺少目标模型时新建模型。"""

        model = FakeGeometryModel(self.events)
        self.models[name] = model
        return model

    def save(self):
        """记录工作副本保存。"""

        self.events.append(("save", self.pathName))


def _plan():
    """构造一份桌面端真实签名的材料计划。"""

    state = MaterialElasticState(
        model_name="Model-1",
        material_name="Steel",
        youngs_modulus=200000.0,
        poisson_ratio=0.3,
        stress_unit="MPa",
        fingerprint=compute_material_fingerprint(
            "Model-1", "Steel", 200000.0, 0.3
        ),
    )
    request = parse_material_command(
        "把 Model-1 中 Steel 的弹性模量改为 210000 MPa"
    )
    return build_material_plan(request, state)


def _rectangle_plan():
    """构造桌面端真实签名的矩形板计划。"""

    request = parse_rectangle_command(
        "创建一个长 100 mm、宽 20 mm 的二维矩形板，"
        "模型名 Model-1，零件名 Plate"
    )
    return build_rectangle_plan(
        request,
        snapshot_fingerprint="c" * 64,
        model_exists=True,
        part_exists=False,
    )


class Abaqus2021MaterialExecutorTests(unittest.TestCase):
    """确认固定动作可执行，任意脚本和危险保存方式不存在。"""

    def test_gui_uses_fox_timer_and_fixed_kernel_call_without_thread(self):
        """GUI 必须在事件循环中转发安全 ID，不开后台线程。"""

        source = GUI_PATH.read_text(encoding="utf-8")
        self.assertIn("addTimeout", source)
        self.assertIn("safe_material_action_kernel.process_request(%r)", source)
        self.assertIn("os.path.abspath(__file__)", source)
        self.assertIn("sys.path.insert(0, _aca_plugin_directory)", source)
        self.assertIn("SafeActionPump.onTimeout", source)
        self.assertNotIn("self.ID_TIMEOUT, self.onTimeout", source)
        self.assertNotIn("import threading", source)
        self.assertNotIn("exec(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("execute_script", source)

    def test_kernel_source_has_no_arbitrary_execution_or_blocking_job_wait(self):
        """Kernel 只允许固定 Job 提交，不得隐藏脚本或阻塞等待。"""

        source = KERNEL_PATH.read_text(encoding="utf-8")
        self.assertNotIn("exec(", source)
        self.assertNotIn("eval(", source)
        self.assertNotIn("subprocess", source)
        self.assertIn("job.submit(consistencyChecking=ON)", source)
        self.assertNotIn("waitForCompletion", source)
        self.assertIn("elastic.setValues", source)
        self.assertNotIn("mdb.saveAs", source)
        self.assertIn("shutil.copy2", source)
        self.assertIn("def _open_protected_working_copy(", source)
        self.assertIn("abaqus_module.openMdb", source)
        self.assertIn("def _restore_original(", source)
        self.assertIn("def _refresh_readonly_snapshot():", source)
        self.assertIn("readonly_model_snapshot_kernel.py", source)

    def test_kernel_converts_json_unicode_names_for_abaqus_repository(self):
        """Python 2 的 JSON Unicode 名称不能直接交给部分 Abaqus Repository。"""

        source = KERNEL_PATH.read_text(encoding="utf-8")
        self.assertIn("def _repository_key(value):", source)
        self.assertIn("database.models[_repository_key(model_name)]", source)
        self.assertIn("model.materials[_repository_key(material_name)]", source)

    def test_report_writer_is_python27_compatible_and_never_overwrites(self):
        """报告写入不能使用 Python 3 专属的 xb，并且必须拒绝覆盖。"""

        module = _load_kernel()
        source = KERNEL_PATH.read_text(encoding="utf-8")
        self.assertNotIn('io.open(report_path, "xb")', source)
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "result_report_zh_001.md"
            module._write_new_report(str(report_path), b"first")
            self.assertEqual(report_path.read_bytes(), b"first")
            with self.assertRaises(module.SafeActionFailure) as context:
                module._write_new_report(str(report_path), b"second")
            self.assertEqual(context.exception.code, "REPORT_EXISTS")
            self.assertEqual(report_path.read_bytes(), b"first")

    def test_apply_saves_new_copy_before_changing_elastic(self):
        """真实写动作必须先另存，随后改值，最后保存工作副本。"""

        module = _load_kernel()
        events = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.cae"
            original.write_bytes(b"unchanged-original")
            elastic = FakeElastic(events)
            fake_mdb = FakeMdb(original, elastic, events)
            fake_abaqus = FakeAbaqus(fake_mdb, events)
            with patch.dict(sys.modules, {"abaqus": fake_abaqus}), patch.dict(
                os.environ, {"LOCALAPPDATA": str(root)}
            ):
                receipt = module._apply(_plan())

            self.assertEqual([event[0] for event in events], ["openMdb", "setValues", "save"])
            self.assertNotEqual(Path(events[0][1]), original)
            self.assertEqual(original.read_bytes(), b"unchanged-original")
            self.assertTrue(Path(events[0][1]).is_file())
            self.assertFalse(
                Path(events[0][1] + ".aca_original_snapshot").exists()
            )
            self.assertEqual(elastic.table, ((210000.0, 0.3),))
            self.assertEqual(Path(events[0][1]).name, receipt["working_copy_name"])
            self.assertNotIn("path", receipt)

    def test_rectangle_action_creates_only_fixed_two_dimensional_geometry(self):
        """模拟执行应先开副本，再按计划创建矩形板并保存。"""

        module = _load_kernel()
        events = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "rectangle-original.cae"
            original.write_bytes(b"unchanged-rectangle-original")
            fake_mdb = FakeGeometryMdb(original, events)
            fake_abaqus = FakeAbaqus(fake_mdb, events)
            fake_constants = SimpleNamespace(
                TWO_D_PLANAR="TWO_D_PLANAR",
                DEFORMABLE_BODY="DEFORMABLE_BODY",
            )
            with patch.dict(
                sys.modules,
                {"abaqus": fake_abaqus, "abaqusConstants": fake_constants},
            ), patch.dict(os.environ, {"LOCALAPPDATA": str(root)}):
                receipt = module._apply_rectangle(_rectangle_plan())

            names = [event[0] for event in events]
            self.assertEqual(
                names,
                ["openMdb", "ConstrainedSketch", "rectangle", "Part", "BaseShell", "save"],
            )
            self.assertEqual(events[2][1:], ((0.0, 0.0), (100.0, 20.0)))
            self.assertEqual(original.read_bytes(), b"unchanged-rectangle-original")
            self.assertEqual(receipt["part"], "Plate")
            self.assertTrue(receipt["original_untouched"])

    def test_stale_fingerprint_stops_before_save_as(self):
        """预览后旧值变化时不能创建副本或修改材料。"""

        module = _load_kernel()
        events = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            elastic = FakeElastic(events)
            elastic.table = ((205000.0, 0.3),)
            fake_mdb = FakeMdb(root / "original.cae", elastic, events)
            with patch.dict(sys.modules, {"abaqus": FakeAbaqus(fake_mdb, events)}), patch.dict(
                os.environ, {"LOCALAPPDATA": str(root)}
            ):
                with self.assertRaises(module.SafeActionFailure) as captured:
                    module._apply(_plan())
            self.assertIn(captured.exception.code, ("STALE_BEFORE_VALUE", "STALE_MODEL_FINGERPRINT"))
            self.assertEqual(events, [])

    def test_same_plan_digest_cannot_be_applied_twice(self):
        """同一计划的第二次应用必须在另存前停止。"""

        module = _load_kernel()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = _plan()
            original = root / "original.cae"
            original.write_bytes(b"unchanged-original")
            first_events = []
            first_mdb = FakeMdb(original, FakeElastic(first_events), first_events)
            with patch.dict(sys.modules, {"abaqus": FakeAbaqus(first_mdb, first_events)}), patch.dict(
                os.environ, {"LOCALAPPDATA": str(root)}
            ):
                module._apply(plan)
                second_events = []
                second_mdb = FakeMdb(original, FakeElastic(second_events), second_events)
                sys.modules["abaqus"] = FakeAbaqus(second_mdb, second_events)
                with self.assertRaises(module.SafeActionFailure) as captured:
                    module._apply(plan)
            self.assertEqual(captured.exception.code, "PLAN_ALREADY_USED")
            self.assertEqual(second_events, [])

    def test_processing_request_rejects_unknown_type(self):
        """协议中不存在的动作类型只能返回固定错误码。"""

        module = _load_kernel()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            processing = root / "AbaqusCodexAssistant" / "safe_actions" / "processing"
            processing.mkdir(parents=True)
            request_id = "aca_0123456789abcdef0123"
            envelope = {
                "protocol": module.PROTOCOL,
                "id": request_id,
                "type": "execute_script",
                "created_at": time.time(),
                "expires_at": time.time() + 5,
            }
            (processing / ("cmd_" + request_id + ".json")).write_text(
                json.dumps(envelope), encoding="utf-8"
            )
            fake_uti = SimpleNamespace(getVersion=lambda: "2021")
            with patch.dict(os.environ, {"LOCALAPPDATA": str(root)}), patch.dict(
                sys.modules, {"uti": fake_uti}
            ):
                self.assertFalse(module.process_request(request_id))
            result = json.loads(
                (
                    root
                    / "AbaqusCodexAssistant"
                    / "safe_actions"
                    / "results"
                    / (request_id + ".json")
                ).read_text(encoding="ascii")
            )
            self.assertEqual(result["error_code"], "INVALID_REQUEST")
            self.assertNotIn("error_message", result)


if __name__ == "__main__":
    unittest.main()
