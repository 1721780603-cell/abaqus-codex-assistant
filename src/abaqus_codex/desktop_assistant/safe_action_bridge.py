# -*- coding: utf-8 -*-
"""通过项目自有白名单文件协议连接 Abaqus 2021 GUI 插件。"""

from __future__ import annotations

import json
import math
import os
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional

from abaqus_codex.assistant_protocol import (
    ActionPlanValidationError,
    validate_action_plan,
)
from abaqus_codex.desktop_assistant.material_flow import (
    MaterialElasticState,
    normalize_material_state,
)
from abaqus_codex.mcp_guard import process_is_running


PROTOCOL_NAME = "abaqus-codex-safe-actions/1"
STATUS_SCHEMA = "abaqus-codex-safe-action-status/1"
TARGET_RELEASE = "2021"
MAX_REQUEST_BYTES = 256 * 1024
MAX_RESULT_BYTES = 256 * 1024
MAX_STATUS_BYTES = 16 * 1024
DEFAULT_STATUS_MAX_AGE_SECONDS = 5.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.05


SAFE_ERROR_MESSAGES = {
    "WRONG_VERSION": "安全执行器只支持 Abaqus 2021。",
    "MODEL_NOT_FOUND": "指定模型不存在，请重新读取模型。",
    "PART_ALREADY_EXISTS": "指定模型中已经有同名零件，为避免覆盖已停止执行。",
    "PART_NOT_FOUND": "指定零件不存在，请按向导先完成几何步骤。",
    "MATERIAL_ALREADY_EXISTS": "指定材料已经存在，向导不会覆盖；可改用材料修改命令。",
    "SECTION_ALREADY_EXISTS": "指定截面已经存在，向导不会覆盖。",
    "SECTION_NOT_FOUND": "指定截面不存在，请先完成截面步骤。",
    "INSTANCE_ALREADY_EXISTS": "指定实例已经存在，向导不会覆盖。",
    "INSTANCE_NOT_FOUND": "指定实例不存在，请先完成装配步骤。",
    "STEP_ALREADY_EXISTS": "指定分析步已经存在，向导不会覆盖。",
    "STEP_NOT_FOUND": "指定分析步不存在，请先完成分析步步骤。",
    "BC_ALREADY_EXISTS": "矩形板拉伸边界条件已经存在，向导不会覆盖。",
    "MESH_ALREADY_EXISTS": "零件已经有网格，向导不会隐式删除或重划。",
    "EMPTY_GEOMETRY": "零件几何不完整，无法完成当前向导步骤。",
    "JOB_ALREADY_EXISTS": "指定 Job 已经存在，禁止覆盖或重复提交。",
    "JOB_NOT_FOUND": "没有找到指定 Job，请先完成 Job 提交步骤。",
    "JOB_NOT_COMPLETED": "Job 尚未成功完成，请稍等后重新生成结果计划。",
    "ODB_INVALID": "ODB 缺少可用的 U 或 S 结果，无法生成报告。",
    "REPORT_EXISTS": "同名中文报告已经存在；为避免覆盖已停止。",
    "MATERIAL_NOT_FOUND": "指定材料不存在，请重新读取模型。",
    "ELASTIC_NOT_FOUND": "材料没有可读取的线弹性行为。",
    "UNSUPPORTED_ELASTIC_TYPE": "第一版只支持已有的各向同性线弹性材料。",
    "DEPENDENT_ELASTIC_NOT_SUPPORTED": "第一版不修改温度或场变量相关的弹性表。",
    "COMPLEX_ELASTIC_TABLE": "第一版只支持单行 E/泊松比弹性表。",
    "STALE_BEFORE_VALUE": "材料旧值已经变化，请重新生成修改计划。",
    "STALE_MODEL_FINGERPRINT": "材料状态已经变化，请重新生成修改计划。",
    "UNSAVED_DATABASE": "请先在 Abaqus 中保存当前 CAE 文件，再应用修改。",
    "SAVE_AS_FAILED": "无法创建受保护工作副本；材料没有修改。",
    "PLAN_ALREADY_USED": "这个计划已经领取过，不能重复应用。",
    "PLAN_EXPIRED": "修改计划已经过期，请重新生成。",
    "INVALID_REQUEST": "安全执行器拒绝了不符合白名单的请求。",
    "INVALID_PLAN": "修改计划没有通过 Abaqus 端的二次校验。",
    "POSTCONDITION_FAILED": "Abaqus 返回的新值与计划不一致，已尝试恢复工作副本。",
    "UNEXPECTED_APPLY_FAILURE": "执行遇到本地错误；原 CAE 文件不会被覆盖。",
    "SNAPSHOT_REFRESH_FAILED": "Abaqus 没有完成当前模型只读摘要刷新。",
}


class SafeActionBridgeError(RuntimeError):
    """表示安全动作桥接没有明确成功。"""


class SafeActionOfflineError(SafeActionBridgeError):
    """表示 Abaqus GUI 安全插件不在线。"""


class SafeActionProtocolError(SafeActionBridgeError):
    """表示请求或结果不符合固定协议。"""


class SafeActionTimeoutError(SafeActionBridgeError):
    """表示请求尚未被 Abaqus 明确完成。"""

    def __init__(self, message: str, *, outcome_unknown: bool) -> None:
        """记录写动作是否可能已经被领取，便于界面禁止盲目重试。"""

        super().__init__(message)
        self.outcome_unknown = outcome_unknown


def default_safe_action_home() -> Path:
    """返回桌面端和 Abaqus GUI 插件共同使用的固定本地目录。"""

    local_data = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local_data) if local_data else Path.home()
    return (base / "AbaqusCodexAssistant" / "safe_actions").resolve()


def _read_limited_json(path: Path, maximum: int, label: str) -> Dict[str, object]:
    """从同一文件句柄限量读取完整 JSON 对象。"""

    try:
        with path.open("rb") as stream:
            raw = stream.read(maximum + 1)
    except OSError as error:
        raise SafeActionProtocolError("{0}暂时无法读取。".format(label)) from error
    if len(raw) > maximum:
        raise SafeActionProtocolError("{0}超过安全大小上限。".format(label))
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise SafeActionProtocolError("{0}不是完整 UTF-8 JSON。".format(label)) from error
    if not isinstance(value, dict):
        raise SafeActionProtocolError("{0}必须是 JSON 对象。".format(label))
    return value


def inspect_safe_action_status(
    status_file: Path,
    *,
    now: Optional[float] = None,
    max_age_seconds: float = DEFAULT_STATUS_MAX_AGE_SECONDS,
    process_checker: Callable[[int], bool] = process_is_running,
) -> Dict[str, object]:
    """只读检查 GUI 事件循环插件的状态和原进程。"""

    if max_age_seconds <= 0:
        raise ValueError("安全插件状态有效期必须大于零。")
    try:
        status = _read_limited_json(status_file, MAX_STATUS_BYTES, "状态文件")
    except SafeActionProtocolError:
        return {
            "responsive": False,
            "status": "missing-or-invalid",
            "message": "没有发现可用的 Abaqus 安全动作插件状态。",
        }

    expected_fields = {
        "schema",
        "version",
        "abaqus_release",
        "status",
        "timestamp",
        "pid",
        "message",
    }
    if set(status) != expected_fields:
        return {
            "responsive": False,
            "status": "invalid",
            "message": "Abaqus 安全动作插件状态格式无效。",
        }
    timestamp = status["timestamp"]
    pid = status["pid"]
    if (
        status["schema"] != STATUS_SCHEMA
        or status["abaqus_release"] != TARGET_RELEASE
        or status["status"] != "running"
        or isinstance(timestamp, bool)
        or not isinstance(timestamp, (int, float))
        or not math.isfinite(float(timestamp))
        or isinstance(pid, bool)
        or not isinstance(pid, int)
        or pid <= 0
    ):
        return {
            "responsive": False,
            "status": "invalid",
            "message": "Abaqus 安全动作插件没有通过版本或状态校验。",
        }
    current_time = time.time() if now is None else float(now)
    age = current_time - float(timestamp)
    if age < -5.0:
        return {
            "responsive": False,
            "status": "future",
            "message": "安全插件时间位于未来，请检查系统时间。",
        }
    if age > max_age_seconds:
        return {
            "responsive": False,
            "status": "stale",
            "message": "Abaqus 安全动作插件状态已经过期。",
        }
    if not process_checker(pid):
        return {
            "responsive": False,
            "status": "dead-process",
            "message": "安全插件记录的 Abaqus GUI 进程已经关闭。",
        }
    return {
        "responsive": True,
        "status": "running",
        "message": "Abaqus 2021 安全动作插件在线。",
        "pid": pid,
        "age_seconds": max(0.0, age),
    }


class SafeActionFileBridge:
    """只暴露快照、材料和矩形板的固定白名单方法。"""

    is_mock = False
    mode_name = "安全动作"

    def __init__(
        self,
        home: Optional[Path] = None,
        *,
        status_max_age_seconds: float = DEFAULT_STATUS_MAX_AGE_SECONDS,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        process_checker: Callable[[int], bool] = process_is_running,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """保存固定目录和可替换时钟，便于完全离线测试。"""

        if status_max_age_seconds <= 0 or poll_interval_seconds <= 0:
            raise ValueError("状态有效期和轮询间隔必须大于零。")
        self.home = (home or default_safe_action_home()).resolve()
        self.status_file = self.home / "status.json"
        self.requests_dir = self.home / "requests"
        self.approved_dir = self.home / "approved"
        self.processing_dir = self.home / "processing"
        self.results_dir = self.home / "results"
        self.status_max_age_seconds = float(status_max_age_seconds)
        self.poll_interval_seconds = float(poll_interval_seconds)
        self.process_checker = process_checker
        self.wall_clock = wall_clock
        self.monotonic_clock = monotonic_clock
        self.sleeper = sleeper

    def inspect_status(self) -> Dict[str, object]:
        """检查插件状态；离线时不会创建请求目录。"""

        return inspect_safe_action_status(
            self.status_file,
            now=self.wall_clock(),
            max_age_seconds=self.status_max_age_seconds,
            process_checker=self.process_checker,
        )

    def inspect_material_elastic(
        self,
        model_name: str,
        material_name: str,
        *,
        timeout_seconds: float = 5.0,
    ) -> MaterialElasticState:
        """让 Kernel 主线程读取一个材料的简单弹性旧值。"""

        result = self._exchange(
            "inspect_material_elastic",
            {
                "target": {
                    "model": str(model_name),
                    "material": str(material_name),
                }
            },
            approved=False,
            timeout_seconds=timeout_seconds,
        )
        data = result.get("data")
        if not isinstance(data, Mapping):
            raise SafeActionProtocolError("材料读取结果缺少 data 对象。")
        return normalize_material_state(data)

    def refresh_readonly_snapshot(
        self, *, timeout_seconds: float = 5.0
    ) -> None:
        """请求 Abaqus 用现有白名单模块生成一次当前模型摘要。"""

        result = self._exchange(
            "refresh_readonly_snapshot",
            {},
            approved=False,
            timeout_seconds=timeout_seconds,
        )
        data = result.get("data")
        if data != {"refreshed": True}:
            raise SafeActionProtocolError("只读摘要刷新回执格式无效。")

    def apply_material_plan(
        self,
        plan: Mapping[str, object],
        *,
        timeout_seconds: float = 30.0,
    ) -> Dict[str, object]:
        """只发送已校验、单动作且要求工作副本的材料计划。"""

        try:
            checked = validate_action_plan(plan)
        except ActionPlanValidationError as error:
            raise SafeActionProtocolError("修改计划已经失效，请重新生成。") from error
        actions = checked["actions"]
        if (
            len(actions) != 1
            or actions[0]["type"] != "set_material_elastic"
            or checked["requires_backup"] is not True
            or checked["requires_job_confirmation"] is not False
        ):
            raise SafeActionProtocolError("第一版只允许一个材料弹性修改动作。")
        result = self._exchange(
            "apply_material_plan",
            {"plan": checked},
            approved=True,
            timeout_seconds=timeout_seconds,
        )
        data = result.get("data")
        if not isinstance(data, dict):
            raise SafeActionProtocolError("材料修改回执缺少 data 对象。")
        required = {
            "plan_id",
            "action_id",
            "model",
            "material",
            "before",
            "after",
            "working_copy_name",
            "same_directory",
            "original_untouched",
        }
        if set(data) != required:
            raise SafeActionProtocolError("材料修改回执字段不完整。")
        if (
            data["plan_id"] != checked["plan_id"]
            or data["action_id"] != actions[0]["id"]
            or data["model"] != checked["model_name"]
            or data["material"] != actions[0]["target"]["material"]
            or data["same_directory"] is not True
            or data["original_untouched"] is not True
        ):
            raise SafeActionProtocolError("材料修改回执与本次计划不一致。")
        working_copy_name = data["working_copy_name"]
        if (
            not isinstance(working_copy_name, str)
            or not working_copy_name.lower().endswith(".cae")
            or Path(working_copy_name).name != working_copy_name
        ):
            raise SafeActionProtocolError("工作副本文件名不安全。")
        return dict(data)

    def apply_rectangle_plan(
        self,
        plan: Mapping[str, object],
        *,
        timeout_seconds: float = 30.0,
    ) -> Dict[str, object]:
        """只发送单个二维矩形板创建动作。"""

        try:
            checked = validate_action_plan(plan)
        except ActionPlanValidationError as error:
            raise SafeActionProtocolError("几何计划已经失效，请重新生成。") from error
        actions = checked["actions"]
        if (
            len(actions) != 1
            or actions[0]["type"] != "create_rectangle_part"
            or checked["requires_backup"] is not True
            or checked["requires_job_confirmation"] is not False
        ):
            raise SafeActionProtocolError("第一版只允许一个二维矩形板创建动作。")
        result = self._exchange(
            "apply_rectangle_plan",
            {"plan": checked},
            approved=True,
            timeout_seconds=timeout_seconds,
        )
        data = result.get("data")
        if not isinstance(data, dict):
            raise SafeActionProtocolError("几何修改回执缺少 data 对象。")
        required = {
            "plan_id",
            "action_id",
            "model",
            "part",
            "length",
            "width",
            "length_unit",
            "working_copy_name",
            "same_directory",
            "original_untouched",
        }
        action = actions[0]
        if set(data) != required or (
            data["plan_id"] != checked["plan_id"]
            or data["action_id"] != action["id"]
            or data["model"] != checked["model_name"]
            or data["part"] != action["target"]["part"]
            or data["same_directory"] is not True
            or data["original_untouched"] is not True
        ):
            raise SafeActionProtocolError("几何修改回执与本次计划不一致。")
        working_copy_name = data["working_copy_name"]
        if (
            not isinstance(working_copy_name, str)
            or not working_copy_name.lower().endswith(".cae")
            or Path(working_copy_name).name != working_copy_name
        ):
            raise SafeActionProtocolError("工作副本文件名不安全。")
        return dict(data)

    def apply_guided_plan(
        self,
        plan: Mapping[str, object],
        *,
        timeout_seconds: float = 30.0,
    ) -> Dict[str, object]:
        """发送第 2–10 步中的一个固定向导动作。"""

        try:
            checked = validate_action_plan(plan)
        except ActionPlanValidationError as error:
            raise SafeActionProtocolError("向导计划已经失效，请重新生成。") from error
        actions = checked["actions"]
        allowed_types = {
            "set_material_elastic": "material",
            "create_section_assignment": "section",
            "create_instance": "assembly",
            "create_static_step": "step",
            "configure_rectangle_tension_bcs": "bcs",
            "set_mesh_size": "mesh",
            "create_submit_job": "job",
            "read_job_results_report": "results",
        }
        if len(actions) != 1 or actions[0]["type"] not in allowed_types:
            raise SafeActionProtocolError("向导计划必须只包含一个固定步骤动作。")
        action = actions[0]
        stage = allowed_types[action["type"]]
        if checked["requires_backup"] is not (stage != "results"):
            raise SafeActionProtocolError("向导计划的 CAE 备份标志不一致。")
        if checked["requires_job_confirmation"] is not (stage == "job"):
            raise SafeActionProtocolError("向导计划的 Job 确认标志不一致。")
        result = self._exchange(
            "apply_guided_plan",
            {"plan": checked},
            approved=True,
            timeout_seconds=timeout_seconds,
        )
        data = result.get("data")
        if not isinstance(data, dict):
            raise SafeActionProtocolError("向导回执缺少 data 对象。")
        if stage == "results":
            return self._validate_results_receipt(checked, action, data)
        return self._validate_guided_write_receipt(
            checked, action, stage, data
        )

    def _validate_guided_write_receipt(
        self,
        plan: Mapping[str, object],
        action: Mapping[str, object],
        stage: str,
        data: Mapping[str, object],
    ) -> Dict[str, object]:
        """严格核对一个会修改 CAE 的向导回执。"""

        required = {
            "plan_id",
            "action_id",
            "stage",
            "model",
            "details",
            "working_copy_name",
            "same_directory",
            "original_untouched",
        }
        if set(data) != required or (
            data["plan_id"] != plan["plan_id"]
            or data["action_id"] != action["id"]
            or data["stage"] != stage
            or data["model"] != plan["model_name"]
            or data["same_directory"] is not True
            or data["original_untouched"] is not True
        ):
            raise SafeActionProtocolError("向导回执与本次计划不一致。")
        working_name = data["working_copy_name"]
        if (
            not isinstance(working_name, str)
            or not working_name.lower().endswith(".cae")
            or Path(working_name).name != working_name
        ):
            raise SafeActionProtocolError("工作副本文件名不安全。")
        details = data["details"]
        expected_fields = {
            "material": {"material", "youngs_modulus", "poisson_ratio", "stress_unit"},
            "section": {"part", "section", "material", "thickness", "length_unit"},
            "assembly": {"part", "instance", "dependent"},
            "step": {"step", "previous_step", "field_output"},
            "bcs": {"instance", "step", "right_displacement", "length_unit", "bc_names"},
            "mesh": {"part", "size", "length_unit", "element_count", "node_count", "element_types"},
            "job": {"job", "num_cpus", "status"},
        }[stage]
        if not isinstance(details, dict) or set(details) != expected_fields:
            raise SafeActionProtocolError("向导回执详情字段不完整。")
        # 所有文本详情都只允许对象名或固定短文本，不能夹带本机路径。
        for value in details.values():
            if isinstance(value, str) and ("\\" in value or "/" in value):
                raise SafeActionProtocolError("向导回执详情包含不允许的路径。")
        return dict(data)

    def _validate_results_receipt(
        self,
        plan: Mapping[str, object],
        action: Mapping[str, object],
        data: Mapping[str, object],
    ) -> Dict[str, object]:
        """核对固定 ODB 极值和报告文件名，不接受路径。"""

        required = {
            "plan_id",
            "action_id",
            "stage",
            "model",
            "job",
            "maximum_displacement",
            "maximum_mises_stress",
            "length_unit",
            "stress_unit",
            "report_name",
            "cae_unchanged",
        }
        if set(data) != required or (
            data["plan_id"] != plan["plan_id"]
            or data["action_id"] != action["id"]
            or data["stage"] != "results"
            or data["model"] != plan["model_name"]
            or data["job"] != action["target"]["job"]
            or data["length_unit"] != "mm"
            or data["stress_unit"] != "MPa"
            or data["cae_unchanged"] is not True
        ):
            raise SafeActionProtocolError("结果回执与本次计划不一致。")
        for field in ("maximum_displacement", "maximum_mises_stress"):
            value = data[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) < 0.0
            ):
                raise SafeActionProtocolError("结果回执包含无效极值。")
        report_name = data["report_name"]
        if (
            not isinstance(report_name, str)
            or not report_name.lower().endswith(".md")
            or Path(report_name).name != report_name
        ):
            raise SafeActionProtocolError("报告文件名不安全。")
        return dict(data)

    def _exchange(
        self,
        request_type: str,
        body: Mapping[str, object],
        *,
        approved: bool,
        timeout_seconds: float,
    ) -> Dict[str, object]:
        """原子发布一个固定类型请求，并只等待自己的结果文件。"""

        allowed = {
            "inspect_material_elastic": False,
            "refresh_readonly_snapshot": False,
            "apply_rectangle_plan": True,
            "apply_material_plan": True,
            "apply_guided_plan": True,
        }
        if request_type not in allowed or allowed[request_type] is not approved:
            raise SafeActionProtocolError("请求类型不在安全白名单中。")
        maximum_timeout = 60.0 if approved else 10.0
        if not 0.1 <= float(timeout_seconds) <= maximum_timeout:
            raise ValueError("请求超时不在允许范围内。")
        health = self.inspect_status()
        if not health.get("responsive"):
            raise SafeActionOfflineError(str(health.get("message", "安全插件离线。")))

        queue_directory = self.approved_dir if approved else self.requests_dir
        try:
            queue_directory.mkdir(parents=True, exist_ok=True)
            self.results_dir.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise SafeActionBridgeError("无法访问安全动作目录。") from error

        request_id = "aca_" + uuid.uuid4().hex[:20]
        final_path = queue_directory / ("cmd_{0}.json".format(request_id))
        temporary_path = queue_directory / ("cmd_{0}.tmp".format(request_id))
        processing_path = self.processing_dir / ("cmd_{0}.json".format(request_id))
        result_path = self.results_dir / ("{0}.json".format(request_id))
        created_at = self.wall_clock()
        request = {
            "protocol": PROTOCOL_NAME,
            "id": request_id,
            "type": request_type,
            "created_at": created_at,
            "expires_at": created_at + float(timeout_seconds),
        }
        request.update(dict(body))
        try:
            encoded = json.dumps(
                request,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError) as error:
            raise SafeActionProtocolError("请求无法安全序列化。") from error
        if len(encoded) > MAX_REQUEST_BYTES:
            raise SafeActionProtocolError("请求超过 256 KiB 安全上限。")

        claimed = False
        try:
            try:
                with temporary_path.open("xb") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(str(temporary_path), str(final_path))
            except OSError as error:
                raise SafeActionBridgeError("无法发布安全动作请求。") from error

            deadline = self.monotonic_clock() + float(timeout_seconds)
            while self.monotonic_clock() < deadline:
                claimed = claimed or processing_path.is_file()
                if result_path.is_file():
                    result = _read_limited_json(
                        result_path, MAX_RESULT_BYTES, "安全动作结果"
                    )
                    return self._validate_result(result, request_id)
                self.sleeper(self.poll_interval_seconds)
            raise SafeActionTimeoutError(
                (
                    "Abaqus 尚未明确返回修改结果；不要重复点击，请重新读取模型确认。"
                    if approved and claimed
                    else "Abaqus 安全插件没有在限定时间内返回。"
                ),
                outcome_unknown=bool(approved and claimed),
            )
        finally:
            # 只删除仍未被插件领取的本次请求；processing 归执行端所有。
            for path in (temporary_path, final_path, result_path):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    pass

    def _validate_result(
        self, result: Mapping[str, object], request_id: str
    ) -> Dict[str, object]:
        """校验固定结果外壳，并把错误码映射为安全中文。"""

        if result.get("protocol") != PROTOCOL_NAME or result.get("id") != request_id:
            raise SafeActionProtocolError("安全动作结果与本次请求不一致。")
        if result.get("success") is True:
            return dict(result)
        code = result.get("error_code")
        if not isinstance(code, str):
            raise SafeActionProtocolError("安全动作失败结果缺少错误码。")
        message = SAFE_ERROR_MESSAGES.get(
            code, "Abaqus 拒绝了这次修改；原 CAE 文件不会被覆盖。"
        )
        raise SafeActionBridgeError("{0}（{1}）".format(message, code))


__all__ = [
    "PROTOCOL_NAME",
    "STATUS_SCHEMA",
    "SafeActionBridgeError",
    "SafeActionFileBridge",
    "SafeActionOfflineError",
    "SafeActionProtocolError",
    "SafeActionTimeoutError",
    "default_safe_action_home",
    "inspect_safe_action_status",
]
