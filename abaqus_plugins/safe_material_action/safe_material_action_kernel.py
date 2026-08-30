# -*- coding: utf-8 -*-
"""Abaqus 2021 Kernel 端的单一材料弹性白名单执行器。"""

import calendar
import hashlib
import io
import json
import math
import os
import re
import shutil
import sys
import time


PROTOCOL = "abaqus-codex-safe-actions/1"
TARGET_RELEASE = "2021"
MAX_BYTES = 256 * 1024
REQUEST_ID_PATTERN = re.compile(r"^aca_[0-9a-f]{20}$")
FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
PLAN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

try:
    TEXT_TYPES = (basestring,)
except NameError:
    TEXT_TYPES = (str,)


class SafeActionFailure(Exception):
    """只携带固定错误码，避免把模型名或路径写入公开结果。"""

    def __init__(self, code):
        Exception.__init__(self, code)
        self.code = code


def _home():
    """返回桌面端与插件共享的固定本地目录。"""

    base = os.environ.get("LOCALAPPDATA", "").strip() or os.path.expanduser("~")
    return os.path.join(base, "AbaqusCodexAssistant", "safe_actions")


def _ensure_directory(path):
    """兼容 Python 2.7 地创建目录。"""

    if os.path.isdir(path):
        return
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise


def _read_json(path):
    """限量读取完整 UTF-8 JSON 对象。"""

    with io.open(path, "rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise SafeActionFailure("INVALID_REQUEST")
    try:
        value = json.loads(raw.decode("utf-8-sig"))
    except Exception:
        raise SafeActionFailure("INVALID_REQUEST")
    if not isinstance(value, dict):
        raise SafeActionFailure("INVALID_REQUEST")
    return value


def _atomic_write(path, value):
    """先写临时文件，再用唯一最终名发布完整结果。"""

    directory = os.path.dirname(path)
    _ensure_directory(directory)
    temporary = path + ".tmp"
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    if not isinstance(encoded, bytes):
        encoded = encoded.encode("ascii")
    if len(encoded) > MAX_BYTES:
        raise SafeActionFailure("INVALID_REQUEST")
    try:
        with io.open(temporary, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, path)
    finally:
        try:
            if os.path.isfile(temporary):
                os.remove(temporary)
        except Exception:
            pass


def _finite_number(value, minimum, maximum, exclusive_minimum=False,
                   exclusive_maximum=False):
    """严格接受有限实数，并拒绝布尔值。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SafeActionFailure("INVALID_PLAN")
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise SafeActionFailure("INVALID_PLAN")
    if number < minimum or (exclusive_minimum and number == minimum):
        raise SafeActionFailure("INVALID_PLAN")
    if number > maximum or (exclusive_maximum and number == maximum):
        raise SafeActionFailure("INVALID_PLAN")
    return number


def _safe_name(value):
    """限制对象名，禁止路径字符和控制字符。"""

    try:
        text_type = unicode
    except NameError:
        text_type = str
    if not isinstance(value, text_type):
        raise SafeActionFailure("INVALID_PLAN")
    if not value or len(value) > 80 or re.search(r'[\\/:*?"<>|]', value):
        raise SafeActionFailure("INVALID_PLAN")
    for character in value:
        if ord(character) < 32 or ord(character) == 127:
            raise SafeActionFailure("INVALID_PLAN")
    return value


def _repository_key(value):
    """把 JSON Unicode 名称转换为 Abaqus 2021 Repository 可用的键。"""

    try:
        unicode_type = unicode
    except NameError:
        return value
    if isinstance(value, unicode_type):
        return value.encode("utf-8")
    return value


def _canonical_digest(value):
    """计算材料指纹使用的 ASCII JSON SHA-256 十六进制值。"""

    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    if not isinstance(encoded, bytes):
        encoded = encoded.encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _plan_digest(value):
    """按桌面端 UTF-8 规则计算带前缀的 Action Plan 摘要。"""

    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if not isinstance(encoded, bytes):
        encoded = encoded.encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _material_fingerprint(model_name, material_name, youngs, poisson):
    """计算材料实时状态指纹，应用前必须再次相等。"""

    value = {
        "model": model_name,
        "material": material_name,
        "youngs_modulus": float(youngs),
        "poisson_ratio": float(poisson),
        "stress_unit": "MPa",
    }
    return "sha256:" + _canonical_digest(value)


def _running_release():
    """使用 Abaqus 2021 实测存在的 uti API 获取年份。"""

    import uti
    return str(uti.getVersion()).strip()


def _simple_elastic(model_name, material_name, database=None):
    """只读取已有单行各向同性线弹性对象。"""

    if database is None:
        from abaqus import mdb
        database = mdb
    try:
        model = database.models[_repository_key(model_name)]
    except Exception:
        raise SafeActionFailure("MODEL_NOT_FOUND")
    try:
        material = model.materials[_repository_key(material_name)]
    except Exception:
        raise SafeActionFailure("MATERIAL_NOT_FOUND")
    try:
        elastic = material.elastic
    except Exception:
        raise SafeActionFailure("ELASTIC_NOT_FOUND")

    # Abaqus 的 SymbolicConstant 转成文字后应为 ISOTROPIC。
    elastic_type = str(getattr(elastic, "type", "ISOTROPIC")).upper()
    if "ISOTROPIC" not in elastic_type:
        raise SafeActionFailure("UNSUPPORTED_ELASTIC_TYPE")
    if bool(getattr(elastic, "temperatureDependency", False)):
        raise SafeActionFailure("DEPENDENT_ELASTIC_NOT_SUPPORTED")
    if int(getattr(elastic, "dependencies", 0)) != 0:
        raise SafeActionFailure("DEPENDENT_ELASTIC_NOT_SUPPORTED")
    try:
        table = elastic.table
        if len(table) != 1 or len(table[0]) != 2:
            raise SafeActionFailure("COMPLEX_ELASTIC_TABLE")
        youngs = _finite_number(table[0][0], 0.0, 1.0e12, True, False)
        poisson = _finite_number(table[0][1], -1.0, 0.5, True, True)
    except SafeActionFailure:
        raise
    except Exception:
        raise SafeActionFailure("COMPLEX_ELASTIC_TABLE")
    return elastic, youngs, poisson


def _inspect(target):
    """读取一个材料旧值，不执行保存或模型写入。"""

    if not isinstance(target, dict) or set(target.keys()) != set(("model", "material")):
        raise SafeActionFailure("INVALID_REQUEST")
    model_name = _safe_name(target["model"])
    material_name = _safe_name(target["material"])
    unused_elastic, youngs, poisson = _simple_elastic(model_name, material_name)
    return {
        "model": model_name,
        "material": material_name,
        "youngs_modulus": youngs,
        "poisson_ratio": poisson,
        "stress_unit": "MPa",
        "fingerprint": _material_fingerprint(
            model_name, material_name, youngs, poisson
        ),
    }


def _refresh_readonly_snapshot():
    """从固定相邻插件目录调用现有只读快照函数。"""

    plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    kernel_path = os.path.join(
        plugin_root,
        "readonly_model_snapshot",
        "readonly_model_snapshot_kernel.py",
    )
    if not os.path.isfile(kernel_path):
        raise SafeActionFailure("SNAPSHOT_REFRESH_FAILED")
    try:
        if sys.version_info[0] < 3:
            import imp
            module = imp.load_source(
                "aca_readonly_model_snapshot_kernel", kernel_path
            )
        else:
            import importlib.util
            specification = importlib.util.spec_from_file_location(
                "aca_readonly_model_snapshot_kernel", kernel_path
            )
            module = importlib.util.module_from_spec(specification)
            specification.loader.exec_module(module)
        refreshed = module.write_readonly_snapshot()
    except Exception:
        raise SafeActionFailure("SNAPSHOT_REFRESH_FAILED")
    if refreshed is not True:
        raise SafeActionFailure("SNAPSHOT_REFRESH_FAILED")
    return {"refreshed": True}


def _parse_utc(value):
    """解析桌面端生成的秒级 UTC 时间。"""

    try:
        return calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        raise SafeActionFailure("INVALID_PLAN")


def _validate_plan(plan):
    """在 Kernel 内独立复核首版单动作计划和摘要签名。"""

    required = set((
        "schema_version", "abaqus_release", "plan_id", "created_at",
        "expires_at", "model_name", "model_fingerprint", "unit_system",
        "actions", "warnings", "requires_backup",
        "requires_job_confirmation", "plan_digest",
    ))
    if not isinstance(plan, dict) or set(plan.keys()) != required:
        raise SafeActionFailure("INVALID_PLAN")
    if plan["schema_version"] != "abaqus.action.v1" or plan["abaqus_release"] != "2021":
        raise SafeActionFailure("INVALID_PLAN")
    if plan["unit_system"] != "mm-N-s-MPa" or plan["requires_backup"] is not True:
        raise SafeActionFailure("INVALID_PLAN")
    if plan["requires_job_confirmation"] is not False:
        raise SafeActionFailure("INVALID_PLAN")
    if not isinstance(plan["plan_id"], TEXT_TYPES) or not PLAN_ID_PATTERN.match(plan["plan_id"]):
        raise SafeActionFailure("INVALID_PLAN")
    if not isinstance(plan["model_fingerprint"], TEXT_TYPES) or not FINGERPRINT_PATTERN.match(plan["model_fingerprint"]):
        raise SafeActionFailure("INVALID_PLAN")
    unsigned = dict(plan)
    supplied_digest = unsigned.pop("plan_digest")
    if supplied_digest != _plan_digest(unsigned):
        raise SafeActionFailure("INVALID_PLAN")
    now = time.time()
    created = _parse_utc(plan["created_at"])
    expires = _parse_utc(plan["expires_at"])
    if expires <= created or expires - created > 600 or now > expires:
        raise SafeActionFailure("PLAN_EXPIRED")
    if created > now + 30:
        raise SafeActionFailure("INVALID_PLAN")
    if not isinstance(plan["actions"], list) or len(plan["actions"]) != 1:
        raise SafeActionFailure("INVALID_PLAN")
    action = plan["actions"][0]
    action_fields = set(("id", "type", "target", "before", "after", "risk", "warnings"))
    if not isinstance(action, dict) or set(action.keys()) != action_fields:
        raise SafeActionFailure("INVALID_PLAN")
    if action["type"] != "set_material_elastic" or action["risk"] != "low":
        raise SafeActionFailure("INVALID_PLAN")
    if not isinstance(action["id"], TEXT_TYPES) or not PLAN_ID_PATTERN.match(action["id"]):
        raise SafeActionFailure("INVALID_PLAN")
    target = action["target"]
    if not isinstance(target, dict) or set(target.keys()) != set(("model", "material")):
        raise SafeActionFailure("INVALID_PLAN")
    model_name = _safe_name(plan["model_name"])
    if _safe_name(target["model"]) != model_name:
        raise SafeActionFailure("INVALID_PLAN")
    material_name = _safe_name(target["material"])
    for values in (action["before"], action["after"]):
        if not isinstance(values, dict) or set(values.keys()) != set(("youngs_modulus", "poisson_ratio", "stress_unit")):
            raise SafeActionFailure("INVALID_PLAN")
        if values["stress_unit"] != "MPa":
            raise SafeActionFailure("INVALID_PLAN")
        _finite_number(values["youngs_modulus"], 0.0, 1.0e12, True, False)
        _finite_number(values["poisson_ratio"], -1.0, 0.5, True, True)
    return action, model_name, material_name


def _validate_rectangle_plan(plan):
    """独立复核二维矩形板单动作计划。"""

    required = set((
        "schema_version", "abaqus_release", "plan_id", "created_at",
        "expires_at", "model_name", "model_fingerprint", "unit_system",
        "actions", "warnings", "requires_backup",
        "requires_job_confirmation", "plan_digest",
    ))
    if not isinstance(plan, dict) or set(plan.keys()) != required:
        raise SafeActionFailure("INVALID_PLAN")
    if (plan["schema_version"] != "abaqus.action.v1" or
            plan["abaqus_release"] != "2021" or
            plan["unit_system"] != "mm-N-s-MPa" or
            plan["requires_backup"] is not True or
            plan["requires_job_confirmation"] is not False):
        raise SafeActionFailure("INVALID_PLAN")
    if (not isinstance(plan["plan_id"], TEXT_TYPES) or
            not PLAN_ID_PATTERN.match(plan["plan_id"]) or
            not isinstance(plan["model_fingerprint"], TEXT_TYPES) or
            not FINGERPRINT_PATTERN.match(plan["model_fingerprint"])):
        raise SafeActionFailure("INVALID_PLAN")
    unsigned = dict(plan)
    supplied_digest = unsigned.pop("plan_digest")
    if supplied_digest != _plan_digest(unsigned):
        raise SafeActionFailure("INVALID_PLAN")
    now = time.time()
    created = _parse_utc(plan["created_at"])
    expires = _parse_utc(plan["expires_at"])
    if expires <= created or expires - created > 600 or now > expires:
        raise SafeActionFailure("PLAN_EXPIRED")
    if created > now + 30:
        raise SafeActionFailure("INVALID_PLAN")
    if not isinstance(plan["actions"], list) or len(plan["actions"]) != 1:
        raise SafeActionFailure("INVALID_PLAN")
    action = plan["actions"][0]
    fields = set(("id", "type", "target", "before", "after", "risk", "warnings"))
    if not isinstance(action, dict) or set(action.keys()) != fields:
        raise SafeActionFailure("INVALID_PLAN")
    if action["type"] != "create_rectangle_part" or action["risk"] != "medium":
        raise SafeActionFailure("INVALID_PLAN")
    if not isinstance(action["id"], TEXT_TYPES) or not PLAN_ID_PATTERN.match(action["id"]):
        raise SafeActionFailure("INVALID_PLAN")
    target = action["target"]
    if not isinstance(target, dict) or set(target.keys()) != set(("model", "part")):
        raise SafeActionFailure("INVALID_PLAN")
    model_name = _safe_name(plan["model_name"])
    if _safe_name(target["model"]) != model_name:
        raise SafeActionFailure("INVALID_PLAN")
    part_name = _safe_name(target["part"])
    before = action["before"]
    if (not isinstance(before, dict) or
            set(before.keys()) != set(("model_exists", "part_exists")) or
            not isinstance(before["model_exists"], bool) or
            before["part_exists"] is not False):
        raise SafeActionFailure("INVALID_PLAN")
    after = action["after"]
    after_fields = set((
        "length", "width", "length_unit", "dimensionality",
        "part_type", "origin",
    ))
    if not isinstance(after, dict) or set(after.keys()) != after_fields:
        raise SafeActionFailure("INVALID_PLAN")
    length = _finite_number(after["length"], 0.0, 1.0e9, True, False)
    width = _finite_number(after["width"], 0.0, 1.0e9, True, False)
    if (after["length_unit"] != "mm" or
            after["dimensionality"] != "TWO_D_PLANAR" or
            after["part_type"] != "DEFORMABLE_BODY" or
            after["origin"] != "lower_left_0_0"):
        raise SafeActionFailure("INVALID_PLAN")
    return action, model_name, part_name, bool(before["model_exists"]), length, width


def _validate_guided_plan(plan):
    """独立复核矩形板第 2–10 步的单动作计划。"""

    required = set((
        "schema_version", "abaqus_release", "plan_id", "created_at",
        "expires_at", "model_name", "model_fingerprint", "unit_system",
        "actions", "warnings", "requires_backup",
        "requires_job_confirmation", "plan_digest",
    ))
    if not isinstance(plan, dict) or set(plan.keys()) != required:
        raise SafeActionFailure("INVALID_PLAN")
    if (plan["schema_version"] != "abaqus.action.v1" or
            plan["abaqus_release"] != "2021" or
            plan["unit_system"] != "mm-N-s-MPa"):
        raise SafeActionFailure("INVALID_PLAN")
    if (not isinstance(plan["plan_id"], TEXT_TYPES) or
            not PLAN_ID_PATTERN.match(plan["plan_id"]) or
            not isinstance(plan["model_fingerprint"], TEXT_TYPES) or
            not FINGERPRINT_PATTERN.match(plan["model_fingerprint"])):
        raise SafeActionFailure("INVALID_PLAN")
    unsigned = dict(plan)
    supplied_digest = unsigned.pop("plan_digest")
    if supplied_digest != _plan_digest(unsigned):
        raise SafeActionFailure("INVALID_PLAN")
    now = time.time()
    created = _parse_utc(plan["created_at"])
    expires = _parse_utc(plan["expires_at"])
    if expires <= created or expires - created > 600 or now > expires:
        raise SafeActionFailure("PLAN_EXPIRED")
    if created > now + 30:
        raise SafeActionFailure("INVALID_PLAN")
    if not isinstance(plan["actions"], list) or len(plan["actions"]) != 1:
        raise SafeActionFailure("INVALID_PLAN")
    action = plan["actions"][0]
    fields = set(("id", "type", "target", "before", "after", "risk", "warnings"))
    if not isinstance(action, dict) or set(action.keys()) != fields:
        raise SafeActionFailure("INVALID_PLAN")
    if not isinstance(action["id"], TEXT_TYPES) or not PLAN_ID_PATTERN.match(action["id"]):
        raise SafeActionFailure("INVALID_PLAN")
    if not isinstance(action["warnings"], list):
        raise SafeActionFailure("INVALID_PLAN")
    model_name = _safe_name(plan["model_name"])
    action_type = action["type"]
    stage_by_type = {
        "set_material_elastic": "material",
        "create_section_assignment": "section",
        "create_instance": "assembly",
        "create_static_step": "step",
        "configure_rectangle_tension_bcs": "bcs",
        "set_mesh_size": "mesh",
        "create_submit_job": "job",
        "read_job_results_report": "results",
    }
    risk_by_stage = {
        "material": "low", "section": "medium", "assembly": "medium",
        "step": "medium", "bcs": "medium", "mesh": "medium",
        "job": "high", "results": "medium",
    }
    if action_type not in stage_by_type:
        raise SafeActionFailure("INVALID_PLAN")
    stage = stage_by_type[action_type]
    if action["risk"] != risk_by_stage[stage]:
        raise SafeActionFailure("INVALID_PLAN")
    if plan["requires_backup"] is not (stage != "results"):
        raise SafeActionFailure("INVALID_PLAN")
    if plan["requires_job_confirmation"] is not (stage == "job"):
        raise SafeActionFailure("INVALID_PLAN")
    target = action["target"]
    if not isinstance(target, dict) or _safe_name(target.get("model")) != model_name:
        raise SafeActionFailure("INVALID_PLAN")
    before = action["before"]
    after = action["after"]

    if stage == "material":
        if set(target.keys()) != set(("model", "material")) or before is not None:
            raise SafeActionFailure("INVALID_PLAN")
        _safe_name(target["material"])
        expected = set(("youngs_modulus", "poisson_ratio", "stress_unit"))
        if not isinstance(after, dict) or set(after.keys()) != expected:
            raise SafeActionFailure("INVALID_PLAN")
        _finite_number(after["youngs_modulus"], 0.0, 1.0e12, True, False)
        _finite_number(after["poisson_ratio"], -1.0, 0.5, True, True)
        if after["stress_unit"] != "MPa":
            raise SafeActionFailure("INVALID_PLAN")
    elif stage == "section":
        expected_target = set(("model", "part", "section", "material"))
        expected_after = set(("thickness", "length_unit", "section_type", "region"))
        if (set(target.keys()) != expected_target or before is not None or
                not isinstance(after, dict) or set(after.keys()) != expected_after):
            raise SafeActionFailure("INVALID_PLAN")
        for key in ("part", "section", "material"):
            _safe_name(target[key])
        _finite_number(after["thickness"], 0.0, 1.0e9, True, False)
        if (after["length_unit"] != "mm" or
                after["section_type"] != "HOMOGENEOUS_SOLID" or
                after["region"] != "ALL_FACES"):
            raise SafeActionFailure("INVALID_PLAN")
    elif stage == "assembly":
        if (set(target.keys()) != set(("model", "part", "instance")) or
                before is not None or not isinstance(after, dict) or
                set(after.keys()) != set(("dependent", "coordinate_system"))):
            raise SafeActionFailure("INVALID_PLAN")
        _safe_name(target["part"])
        _safe_name(target["instance"])
        if after["dependent"] is not True or after["coordinate_system"] != "CARTESIAN":
            raise SafeActionFailure("INVALID_PLAN")
    elif stage == "step":
        if (set(target.keys()) != set(("model", "step")) or before is not None or
                not isinstance(after, dict) or
                set(after.keys()) != set(("previous_step", "time_period", "nlgeom"))):
            raise SafeActionFailure("INVALID_PLAN")
        _safe_name(target["step"])
        _safe_name(after["previous_step"])
        _finite_number(after["time_period"], 0.0, 1.0e12, True, False)
        if not isinstance(after["nlgeom"], bool):
            raise SafeActionFailure("INVALID_PLAN")
    elif stage == "bcs":
        if (set(target.keys()) != set(("model", "instance", "step")) or
                before is not None or not isinstance(after, dict) or
                set(after.keys()) != set(("right_displacement", "length_unit",
                                          "selection_strategy", "bc_names"))):
            raise SafeActionFailure("INVALID_PLAN")
        _safe_name(target["instance"])
        _safe_name(target["step"])
        displacement = _finite_number(
            after["right_displacement"], -1.0e9, 1.0e9, False, False
        )
        if displacement == 0.0 or after["length_unit"] != "mm":
            raise SafeActionFailure("INVALID_PLAN")
        if after["selection_strategy"] != "RECTANGLE_BOUNDING_BOX":
            raise SafeActionFailure("INVALID_PLAN")
        names = after["bc_names"]
        name_fields = set(("left_horizontal", "anchor_vertical", "right_tension"))
        if not isinstance(names, dict) or set(names.keys()) != name_fields:
            raise SafeActionFailure("INVALID_PLAN")
        for value in names.values():
            _safe_name(value)
    elif stage == "mesh":
        if (set(target.keys()) != set(("model", "part")) or
                not isinstance(before, dict) or
                set(before.keys()) != set(("seed_size", "has_mesh")) or
                before["has_mesh"] is not False or before["seed_size"] is not None or
                not isinstance(after, dict) or
                set(after.keys()) != set(("size", "length_unit"))):
            raise SafeActionFailure("INVALID_PLAN")
        _safe_name(target["part"])
        _finite_number(after["size"], 0.0, 1.0e9, True, False)
        if after["length_unit"] != "mm":
            raise SafeActionFailure("INVALID_PLAN")
    elif stage == "job":
        if (set(target.keys()) != set(("model", "job")) or
                not isinstance(before, dict) or
                set(before.keys()) != set(("job_exists",)) or
                before["job_exists"] is not False or not isinstance(after, dict) or
                set(after.keys()) != set(("num_cpus", "submit",
                                          "consistency_checking", "wait", "auto_retry"))):
            raise SafeActionFailure("INVALID_PLAN")
        _safe_name(target["job"])
        cpus = after["num_cpus"]
        if isinstance(cpus, bool) or not isinstance(cpus, int) or cpus < 1 or cpus > 64:
            raise SafeActionFailure("INVALID_PLAN")
        if (after["submit"] is not True or after["consistency_checking"] is not True or
                after["wait"] is not False or after["auto_retry"] is not False):
            raise SafeActionFailure("INVALID_PLAN")
    elif stage == "results":
        if (set(target.keys()) != set(("model", "job")) or before is not None or
                not isinstance(after, dict) or
                set(after.keys()) != set(("odb_source", "report_format",
                                          "report_language", "overwrite"))):
            raise SafeActionFailure("INVALID_PLAN")
        _safe_name(target["job"])
        if (after["odb_source"] != "CURRENT_CAE_JOB_DIRECTORY" or
                after["report_format"] != "markdown" or
                after["report_language"] != "zh-CN" or
                after["overwrite"] is not False):
            raise SafeActionFailure("INVALID_PLAN")
    return action, model_name, stage


def _claim_digest(digest):
    """以排他创建记录计划，保证同一计划不能被再次应用。"""

    directory = os.path.join(_home(), "used")
    _ensure_directory(directory)
    # Windows 文件名不能包含冒号，只使用已经校验的十六进制部分。
    path = os.path.join(directory, digest.split(":", 1)[1] + ".used")
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(descriptor, str(int(time.time())).encode("ascii"))
        os.close(descriptor)
    except OSError:
        raise SafeActionFailure("PLAN_ALREADY_USED")


def _unique_working_copy(original_path):
    """在原目录生成永不覆盖的工作副本名称。"""

    if not original_path:
        raise SafeActionFailure("UNSAVED_DATABASE")
    directory = os.path.dirname(os.path.abspath(original_path))
    stem = os.path.splitext(os.path.basename(original_path))[0]
    # 连续向导每步都会保留一个副本；限制文件名长度，避免 Windows 路径溢出。
    if len(stem) > 96:
        stem = stem[:96]
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    for index in range(1, 1000):
        name = "%s__aca_edit_%s_%03d.cae" % (stem, timestamp, index)
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            return path, name
    raise SafeActionFailure("SAVE_AS_FAILED")


def _file_digest(path):
    """流式计算 CAE 文件摘要，用于确认复制完整且原件未变化。"""

    digest = hashlib.sha256()
    try:
        with io.open(path, "rb") as stream:
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
    except Exception:
        raise SafeActionFailure("SAVE_AS_FAILED")
    return digest.hexdigest()


def _make_protected_copy(original_path, working_path):
    """同时建立工作副本和原件恢复快照。"""

    original_digest = _file_digest(original_path)
    snapshot_path = working_path + ".aca_original_snapshot"
    try:
        shutil.copy2(original_path, snapshot_path)
        shutil.copy2(snapshot_path, working_path)
    except Exception:
        raise SafeActionFailure("SAVE_AS_FAILED")
    if (_file_digest(snapshot_path) != original_digest or
            _file_digest(working_path) != original_digest):
        raise SafeActionFailure("SAVE_AS_FAILED")
    return original_digest, snapshot_path


def _restore_original(snapshot_path, original_path, original_digest):
    """数据库切换后从快照恢复原件，并复核原始字节摘要。"""

    try:
        shutil.copy2(snapshot_path, original_path)
    except Exception:
        raise SafeActionFailure("UNEXPECTED_APPLY_FAILURE")
    if _file_digest(original_path) != original_digest:
        raise SafeActionFailure("UNEXPECTED_APPLY_FAILURE")
    try:
        os.remove(snapshot_path)
    except Exception:
        # 快照不含新模型数据；清理失败不影响原件和工作副本正确性。
        pass


def _open_protected_working_copy(abaqus_module, database):
    """建立并打开工作副本，同时恢复并校验原 CAE。"""

    original_path = getattr(database, "pathName", "")
    working_path, working_name = _unique_working_copy(original_path)
    original_digest, snapshot_path = _make_protected_copy(
        original_path, working_path
    )
    try:
        working_mdb = abaqus_module.openMdb(pathName=working_path)
    except Exception:
        raise SafeActionFailure("SAVE_AS_FAILED")
    _restore_original(snapshot_path, original_path, original_digest)
    return (
        working_mdb,
        working_name,
        original_path,
        original_digest,
    )


def _apply(plan):
    """复核旧值，先复制并打开副本，再只修改副本中的材料。"""

    import abaqus
    mdb = abaqus.mdb
    action, model_name, material_name = _validate_plan(plan)
    elastic, youngs, poisson = _simple_elastic(model_name, material_name)
    before = action["before"]
    if youngs != float(before["youngs_modulus"]) or poisson != float(before["poisson_ratio"]):
        raise SafeActionFailure("STALE_BEFORE_VALUE")
    current_fingerprint = _material_fingerprint(model_name, material_name, youngs, poisson)
    if current_fingerprint != plan["model_fingerprint"]:
        raise SafeActionFailure("STALE_MODEL_FINGERPRINT")

    _claim_digest(plan["plan_digest"])
    working_mdb, working_name, original_path, original_digest = (
        _open_protected_working_copy(abaqus, mdb)
    )

    after = action["after"]
    try:
        # 打开副本后必须重新取得对象，不能沿用原数据库中的 Elastic 引用。
        elastic, copied_youngs, copied_poisson = _simple_elastic(
            model_name, material_name, database=working_mdb
        )
        if copied_youngs != youngs or copied_poisson != poisson:
            raise SafeActionFailure("STALE_BEFORE_VALUE")
        elastic.setValues(table=((float(after["youngs_modulus"]), float(after["poisson_ratio"])),))
        working_mdb.save()
        if _file_digest(original_path) != original_digest:
            raise SafeActionFailure("UNEXPECTED_APPLY_FAILURE")
    except SafeActionFailure:
        raise
    except Exception:
        raise SafeActionFailure("UNEXPECTED_APPLY_FAILURE")
    return {
        "plan_id": plan["plan_id"],
        "action_id": action["id"],
        "model": model_name,
        "material": material_name,
        "before": before,
        "after": after,
        "working_copy_name": working_name,
        "same_directory": True,
        "original_untouched": True,
    }


def _repository_has(repository, name):
    """兼容 Python 2 Repository 地判断对象名是否存在。"""

    try:
        repository[_repository_key(name)]
        return True
    except Exception:
        return False


def _apply_rectangle(plan):
    """在受保护工作副本中创建一个二维矩形板零件。"""

    import abaqus
    from abaqusConstants import DEFORMABLE_BODY, TWO_D_PLANAR

    mdb = abaqus.mdb
    action, model_name, part_name, expected_model, length, width = (
        _validate_rectangle_plan(plan)
    )
    model_exists = _repository_has(mdb.models, model_name)
    if model_exists != expected_model:
        raise SafeActionFailure("STALE_MODEL_FINGERPRINT")
    if model_exists:
        model = mdb.models[_repository_key(model_name)]
        if _repository_has(model.parts, part_name):
            raise SafeActionFailure("PART_ALREADY_EXISTS")

    _claim_digest(plan["plan_digest"])
    working_mdb, working_name, original_path, original_digest = (
        _open_protected_working_copy(abaqus, mdb)
    )
    try:
        if _repository_has(working_mdb.models, model_name):
            model = working_mdb.models[_repository_key(model_name)]
        else:
            model = working_mdb.Model(name=_repository_key(model_name))
        if _repository_has(model.parts, part_name):
            raise SafeActionFailure("PART_ALREADY_EXISTS")

        sketch_name = "ACA_RectangleSketch"
        suffix = 1
        while _repository_has(model.sketches, sketch_name):
            sketch_name = "ACA_RectangleSketch_%03d" % suffix
            suffix += 1
        sketch = model.ConstrainedSketch(
            name=sketch_name,
            sheetSize=max(length, width) * 2.0,
        )
        sketch.rectangle(point1=(0.0, 0.0), point2=(length, width))
        part = model.Part(
            name=_repository_key(part_name),
            dimensionality=TWO_D_PLANAR,
            type=DEFORMABLE_BODY,
        )
        part.BaseShell(sketch=sketch)
        del model.sketches[_repository_key(sketch_name)]
        working_mdb.save()
        if not _repository_has(model.parts, part_name):
            raise SafeActionFailure("POSTCONDITION_FAILED")
        if _file_digest(original_path) != original_digest:
            raise SafeActionFailure("UNEXPECTED_APPLY_FAILURE")
    except SafeActionFailure:
        raise
    except Exception:
        raise SafeActionFailure("UNEXPECTED_APPLY_FAILURE")
    return {
        "plan_id": plan["plan_id"],
        "action_id": action["id"],
        "model": model_name,
        "part": part_name,
        "length": length,
        "width": width,
        "length_unit": "mm",
        "working_copy_name": working_name,
        "same_directory": True,
        "original_untouched": True,
    }


def _required_model(database, model_name):
    """取得既有模型；向导不会隐式猜测或替换模型。"""

    if not _repository_has(database.models, model_name):
        raise SafeActionFailure("MODEL_NOT_FOUND")
    return database.models[_repository_key(model_name)]


def _required_part(model, part_name):
    """取得既有零件。"""

    if not _repository_has(model.parts, part_name):
        raise SafeActionFailure("PART_NOT_FOUND")
    return model.parts[_repository_key(part_name)]


def _preflight_guided(database, action, model_name, stage):
    """在领取计划和创建副本前检查当前步骤的前置对象。"""

    model = _required_model(database, model_name)
    target = action["target"]
    if stage == "material":
        if _repository_has(model.materials, target["material"]):
            raise SafeActionFailure("MATERIAL_ALREADY_EXISTS")
    elif stage == "section":
        part = _required_part(model, target["part"])
        if not _repository_has(model.materials, target["material"]):
            raise SafeActionFailure("MATERIAL_NOT_FOUND")
        if _repository_has(model.sections, target["section"]):
            raise SafeActionFailure("SECTION_ALREADY_EXISTS")
        if len(part.faces) == 0:
            raise SafeActionFailure("EMPTY_GEOMETRY")
    elif stage == "assembly":
        _required_part(model, target["part"])
        if _repository_has(model.rootAssembly.instances, target["instance"]):
            raise SafeActionFailure("INSTANCE_ALREADY_EXISTS")
    elif stage == "step":
        if _repository_has(model.steps, target["step"]):
            raise SafeActionFailure("STEP_ALREADY_EXISTS")
        if not _repository_has(model.steps, action["after"]["previous_step"]):
            raise SafeActionFailure("STEP_NOT_FOUND")
    elif stage == "bcs":
        if not _repository_has(model.rootAssembly.instances, target["instance"]):
            raise SafeActionFailure("INSTANCE_NOT_FOUND")
        if not _repository_has(model.steps, target["step"]):
            raise SafeActionFailure("STEP_NOT_FOUND")
        for name in action["after"]["bc_names"].values():
            if _repository_has(model.boundaryConditions, name):
                raise SafeActionFailure("BC_ALREADY_EXISTS")
    elif stage == "mesh":
        part = _required_part(model, target["part"])
        if len(part.faces) == 0:
            raise SafeActionFailure("EMPTY_GEOMETRY")
        if len(part.elements) > 0:
            raise SafeActionFailure("MESH_ALREADY_EXISTS")
    elif stage == "job":
        if _repository_has(database.jobs, target["job"]):
            raise SafeActionFailure("JOB_ALREADY_EXISTS")
    return model


def _guided_material(model, action):
    """创建一个简单各向同性线弹性材料。"""

    target = action["target"]
    after = action["after"]
    material = model.Material(name=_repository_key(target["material"]))
    material.Elastic(table=((
        float(after["youngs_modulus"]),
        float(after["poisson_ratio"]),
    ),))
    return {
        "material": target["material"],
        "youngs_modulus": float(after["youngs_modulus"]),
        "poisson_ratio": float(after["poisson_ratio"]),
        "stress_unit": "MPa",
    }


def _guided_section(model, action):
    """创建均质实体截面并赋给二维零件的全部面。"""

    import regionToolset

    target = action["target"]
    after = action["after"]
    part = _required_part(model, target["part"])
    model.HomogeneousSolidSection(
        name=_repository_key(target["section"]),
        material=_repository_key(target["material"]),
        thickness=float(after["thickness"]),
    )
    part.SectionAssignment(
        region=regionToolset.Region(faces=part.faces),
        sectionName=_repository_key(target["section"]),
    )
    return {
        "part": target["part"],
        "section": target["section"],
        "material": target["material"],
        "thickness": float(after["thickness"]),
        "length_unit": "mm",
    }


def _guided_assembly(model, action):
    """在默认笛卡尔坐标系中创建依赖实例。"""

    from abaqusConstants import CARTESIAN, ON

    target = action["target"]
    part = _required_part(model, target["part"])
    assembly = model.rootAssembly
    assembly.DatumCsysByDefault(CARTESIAN)
    assembly.Instance(
        name=_repository_key(target["instance"]),
        part=part,
        dependent=ON,
    )
    return {
        "part": target["part"],
        "instance": target["instance"],
        "dependent": True,
    }


def _guided_step(model, action):
    """创建线性静力步和用于报告的 U/S 场输出。"""

    from abaqusConstants import OFF, ON

    target = action["target"]
    after = action["after"]
    model.StaticStep(
        name=_repository_key(target["step"]),
        previous=_repository_key(after["previous_step"]),
        timePeriod=float(after["time_period"]),
        nlgeom=ON if after["nlgeom"] else OFF,
    )
    output_name = "OutputForReport"
    if not _repository_has(model.fieldOutputRequests, output_name):
        model.FieldOutputRequest(
            name=output_name,
            createStepName=_repository_key(target["step"]),
            variables=("S", "U"),
        )
    return {
        "step": target["step"],
        "previous_step": after["previous_step"],
        "field_output": output_name,
    }


def _guided_bcs(model, action):
    """按矩形外包框建立两个约束和一个拉伸位移。"""

    import regionToolset
    from abaqusConstants import UNSET

    target = action["target"]
    after = action["after"]
    assembly = model.rootAssembly
    instance = assembly.instances[_repository_key(target["instance"])]
    try:
        box = instance.vertices.getBoundingBox()
        low = box["low"]
        high = box["high"]
        x_min = float(low[0])
        y_min = float(low[1])
        x_max = float(high[0])
        y_max = float(high[1])
    except Exception:
        raise SafeActionFailure("EMPTY_GEOMETRY")
    tolerance = max(x_max - x_min, y_max - y_min) * 1.0e-6
    if tolerance <= 0.0:
        raise SafeActionFailure("EMPTY_GEOMETRY")
    left_edges = instance.edges.getByBoundingBox(
        xMin=x_min - tolerance,
        xMax=x_min + tolerance,
        yMin=y_min - tolerance,
        yMax=y_max + tolerance,
    )
    right_edges = instance.edges.getByBoundingBox(
        xMin=x_max - tolerance,
        xMax=x_max + tolerance,
        yMin=y_min - tolerance,
        yMax=y_max + tolerance,
    )
    anchor_vertices = instance.vertices.getByBoundingBox(
        xMin=x_min - tolerance,
        xMax=x_min + tolerance,
        yMin=y_min - tolerance,
        yMax=y_min + tolerance,
    )
    if len(left_edges) == 0 or len(right_edges) == 0 or len(anchor_vertices) == 0:
        raise SafeActionFailure("EMPTY_GEOMETRY")
    names = after["bc_names"]
    model.DisplacementBC(
        name=_repository_key(names["left_horizontal"]),
        createStepName="Initial",
        region=regionToolset.Region(edges=left_edges),
        u1=0.0,
        u2=UNSET,
    )
    model.DisplacementBC(
        name=_repository_key(names["anchor_vertical"]),
        createStepName="Initial",
        region=regionToolset.Region(vertices=anchor_vertices),
        u1=UNSET,
        u2=0.0,
    )
    model.DisplacementBC(
        name=_repository_key(names["right_tension"]),
        createStepName=_repository_key(target["step"]),
        region=regionToolset.Region(edges=right_edges),
        u1=float(after["right_displacement"]),
        u2=UNSET,
    )
    return {
        "instance": target["instance"],
        "step": target["step"],
        "right_displacement": float(after["right_displacement"]),
        "length_unit": "mm",
        "bc_names": dict(names),
    }


def _guided_mesh(model, action):
    """为二维板设置 CPS4R/CPS3 单元并生成网格。"""

    import mesh
    from abaqusConstants import CPS3, CPS4R, STANDARD

    target = action["target"]
    size = float(action["after"]["size"])
    part = _required_part(model, target["part"])
    element_quad = mesh.ElemType(elemCode=CPS4R, elemLibrary=STANDARD)
    element_tri = mesh.ElemType(elemCode=CPS3, elemLibrary=STANDARD)
    part.setElementType(
        regions=(part.faces,),
        elemTypes=(element_quad, element_tri),
    )
    part.seedPart(size=size, deviationFactor=0.1, minSizeFactor=0.1)
    part.generateMesh()
    element_count = len(part.elements)
    node_count = len(part.nodes)
    if element_count <= 0 or node_count <= 0:
        raise SafeActionFailure("POSTCONDITION_FAILED")
    return {
        "part": target["part"],
        "size": size,
        "length_unit": "mm",
        "element_count": int(element_count),
        "node_count": int(node_count),
        "element_types": ["CPS4R", "CPS3"],
    }


def _guided_job(database, action):
    """创建并异步提交 Job；不在 Kernel 调用中等待求解。"""

    from abaqusConstants import ON

    target = action["target"]
    cpus = int(action["after"]["num_cpus"])
    job = database.Job(
        name=_repository_key(target["job"]),
        model=_repository_key(target["model"]),
        numCpus=cpus,
    )
    database.save()
    original_directory = os.getcwd()
    job_directory = os.path.dirname(os.path.abspath(database.pathName))
    try:
        os.chdir(job_directory)
        job.submit(consistencyChecking=ON)
    finally:
        os.chdir(original_directory)
    return {
        "job": target["job"],
        "num_cpus": cpus,
        "status": str(getattr(job, "status", "SUBMITTED")),
    }


def _unique_report_path(directory, job_name):
    """为中文 Markdown 报告选择不覆盖的 ASCII 文件名。"""

    base = "%s_report_zh" % _repository_key(job_name)
    for index in range(1, 1000):
        name = "%s_%03d.md" % (base, index)
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            return path, name
    raise SafeActionFailure("REPORT_EXISTS")


def _write_new_report(path, encoded_report):
    """兼容 Python 2.7 地原子新建报告，绝不覆盖已有文件。"""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError:
        # O_EXCL 保证即使两个请求同时写同名文件，也只有一个能成功。
        raise SafeActionFailure("REPORT_EXISTS")
    stream = None
    try:
        stream = os.fdopen(descriptor, "wb")
        descriptor = None
        stream.write(encoded_report)
        stream.close()
        stream = None
    except Exception:
        # 写入中断时删除本次创建的残缺文件，避免下次误认为是完整报告。
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
        if descriptor is not None:
            try:
                os.close(descriptor)
            except Exception:
                pass
        try:
            os.remove(path)
        except Exception:
            pass
        raise SafeActionFailure("UNEXPECTED_APPLY_FAILURE")


def _read_results_report(plan, action, model_name):
    """读取最后结果帧的 U/S 极值并写入不覆盖的中文报告。"""

    from abaqus import mdb
    from odbAccess import openOdb

    job_name = action["target"]["job"]
    if not _repository_has(mdb.jobs, job_name):
        raise SafeActionFailure("JOB_NOT_FOUND")
    cae_path = getattr(mdb, "pathName", "")
    if not cae_path:
        raise SafeActionFailure("UNSAVED_DATABASE")
    cae_digest = _file_digest(cae_path)
    directory = os.path.dirname(os.path.abspath(cae_path))
    odb_path = os.path.join(directory, "%s.odb" % _repository_key(job_name))
    sta_path = os.path.join(directory, "%s.sta" % _repository_key(job_name))
    completed_marker = b"THE ANALYSIS HAS COMPLETED SUCCESSFULLY"
    try:
        with io.open(sta_path, "rb") as stream:
            status_text = stream.read()
    except Exception:
        status_text = b""
    if not os.path.isfile(odb_path) or completed_marker not in status_text:
        raise SafeActionFailure("JOB_NOT_COMPLETED")

    odb = None
    try:
        odb = openOdb(path=odb_path, readOnly=True)
        step_names = list(odb.steps.keys())
        if not step_names:
            raise SafeActionFailure("ODB_INVALID")
        step = odb.steps[step_names[-1]]
        if not step.frames:
            raise SafeActionFailure("ODB_INVALID")
        frame = step.frames[-1]
        if (not _repository_has(frame.fieldOutputs, "U") or
                not _repository_has(frame.fieldOutputs, "S")):
            raise SafeActionFailure("ODB_INVALID")
        maximum_displacement = None
        for value in frame.fieldOutputs["U"].values:
            squared = 0.0
            for component in value.data:
                squared += float(component) ** 2
            magnitude = math.sqrt(squared)
            if maximum_displacement is None or magnitude > maximum_displacement:
                maximum_displacement = magnitude
        maximum_mises = None
        for value in frame.fieldOutputs["S"].values:
            mises = float(value.mises)
            if maximum_mises is None or mises > maximum_mises:
                maximum_mises = mises
        if maximum_displacement is None or maximum_mises is None:
            raise SafeActionFailure("ODB_INVALID")
    finally:
        if odb is not None:
            try:
                odb.close()
            except Exception:
                pass

    report_path, report_name = _unique_report_path(directory, job_name)
    report = u"""# Abaqus 二维矩形板拉伸分析报告

## 基本信息

- 模型：{model}
- Job：{job}
- 单位约定：mm-N-s-MPa

## 结果极值

- 最大位移模：{maximum_displacement:.8g} mm
- 最大 Mises 应力：{maximum_mises:.8g} MPa

## 说明

- 数值取自 ODB 最后一个分析步的最后一帧。
- 本报告不自动判断网格收敛性、边界条件合理性或工程规范符合性。
- 用于论文或生产项目前，请由具备资质的人员复核模型和单位。
""".format(
        model=model_name,
        job=job_name,
        maximum_displacement=float(maximum_displacement),
        maximum_mises=float(maximum_mises),
    )
    _write_new_report(report_path, report.encode("utf-8"))
    if _file_digest(cae_path) != cae_digest:
        raise SafeActionFailure("UNEXPECTED_APPLY_FAILURE")
    return {
        "plan_id": plan["plan_id"],
        "action_id": action["id"],
        "stage": "results",
        "model": model_name,
        "job": job_name,
        "maximum_displacement": float(maximum_displacement),
        "maximum_mises_stress": float(maximum_mises),
        "length_unit": "mm",
        "stress_unit": "MPa",
        "report_name": report_name,
        "cae_unchanged": True,
    }


def _apply_guided(plan):
    """执行一个离线向导步骤；每个 CAE 写步骤都建立新副本。"""

    import abaqus

    action, model_name, stage = _validate_guided_plan(plan)
    if stage == "results":
        _claim_digest(plan["plan_digest"])
        return _read_results_report(plan, action, model_name)

    _preflight_guided(abaqus.mdb, action, model_name, stage)
    _claim_digest(plan["plan_digest"])
    working_mdb, working_name, original_path, original_digest = (
        _open_protected_working_copy(abaqus, abaqus.mdb)
    )
    try:
        model = _preflight_guided(working_mdb, action, model_name, stage)
        if stage == "material":
            details = _guided_material(model, action)
        elif stage == "section":
            details = _guided_section(model, action)
        elif stage == "assembly":
            details = _guided_assembly(model, action)
        elif stage == "step":
            details = _guided_step(model, action)
        elif stage == "bcs":
            details = _guided_bcs(model, action)
        elif stage == "mesh":
            details = _guided_mesh(model, action)
        elif stage == "job":
            details = _guided_job(working_mdb, action)
        else:
            raise SafeActionFailure("INVALID_PLAN")
        if stage != "job":
            working_mdb.save()
        if _file_digest(original_path) != original_digest:
            raise SafeActionFailure("UNEXPECTED_APPLY_FAILURE")
    except SafeActionFailure:
        raise
    except Exception:
        raise SafeActionFailure("UNEXPECTED_APPLY_FAILURE")
    return {
        "plan_id": plan["plan_id"],
        "action_id": action["id"],
        "stage": stage,
        "model": model_name,
        "details": details,
        "working_copy_name": working_name,
        "same_directory": True,
        "original_untouched": True,
    }


def process_request(request_id):
    """由 GUI 只用程序生成 ID 调用，读取 processing 中的固定请求。"""

    if not isinstance(request_id, TEXT_TYPES) or not REQUEST_ID_PATTERN.match(request_id):
        return False
    home = _home()
    request_path = os.path.join(home, "processing", "cmd_%s.json" % request_id)
    result_path = os.path.join(home, "results", "%s.json" % request_id)
    try:
        if _running_release() != TARGET_RELEASE:
            raise SafeActionFailure("WRONG_VERSION")
        request = _read_json(request_path)
        common = set(("protocol", "id", "type", "created_at", "expires_at"))
        if request.get("protocol") != PROTOCOL or request.get("id") != request_id:
            raise SafeActionFailure("INVALID_REQUEST")
        now = time.time()
        if not isinstance(request.get("expires_at"), (int, float)) or now > float(request["expires_at"]):
            raise SafeActionFailure("PLAN_EXPIRED")
        if request.get("type") == "inspect_material_elastic":
            if set(request.keys()) != common | set(("target",)):
                raise SafeActionFailure("INVALID_REQUEST")
            data = _inspect(request["target"])
        elif request.get("type") == "refresh_readonly_snapshot":
            if set(request.keys()) != common:
                raise SafeActionFailure("INVALID_REQUEST")
            data = _refresh_readonly_snapshot()
        elif request.get("type") == "apply_material_plan":
            if set(request.keys()) != common | set(("plan",)):
                raise SafeActionFailure("INVALID_REQUEST")
            data = _apply(request["plan"])
        elif request.get("type") == "apply_rectangle_plan":
            if set(request.keys()) != common | set(("plan",)):
                raise SafeActionFailure("INVALID_REQUEST")
            data = _apply_rectangle(request["plan"])
        elif request.get("type") == "apply_guided_plan":
            if set(request.keys()) != common | set(("plan",)):
                raise SafeActionFailure("INVALID_REQUEST")
            data = _apply_guided(request["plan"])
        else:
            raise SafeActionFailure("INVALID_REQUEST")
        result = {"protocol": PROTOCOL, "id": request_id, "success": True, "data": data}
    except SafeActionFailure as error:
        result = {"protocol": PROTOCOL, "id": request_id, "success": False, "error_code": error.code}
    except Exception:
        result = {"protocol": PROTOCOL, "id": request_id, "success": False, "error_code": "INVALID_REQUEST"}
    try:
        _atomic_write(result_path, result)
    finally:
        try:
            os.remove(request_path)
        except Exception:
            pass
    return bool(result.get("success"))


__all__ = ["process_request"]
