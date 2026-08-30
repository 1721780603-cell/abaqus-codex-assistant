# -*- coding: utf-8 -*-
"""Abaqus 2021 Kernel 端的一次性只读模型快照函数。"""

import io
import json
import os
import time
import uuid


SCHEMA_NAME = "abaqus-codex-readonly-snapshot"
SCHEMA_VERSION = 1
TARGET_RELEASE = "2021"
MAX_MODELS = 50
MAX_NAMES_PER_FIELD = 200
MAX_NAME_LENGTH = 160
MAX_SNAPSHOT_BYTES = 256 * 1024

try:
    text_type = unicode
    binary_type = str
except NameError:
    text_type = str
    binary_type = bytes


def _to_text(value):
    """把 Abaqus repository 名称转换成有限 Unicode 文本。"""

    if isinstance(value, text_type):
        result = value
    elif isinstance(value, binary_type):
        result = value.decode("utf-8", "replace")
    else:
        result = text_type(value)

    cleaned = []
    for character in result:
        code = ord(character)
        if code < 32 or code == 127:
            cleaned.append(u" ")
        else:
            cleaned.append(character)
    return u" ".join(u"".join(cleaned).split())[:MAX_NAME_LENGTH]


def _running_release():
    """通过 Abaqus 2021 自带的 uti 模块读取发行年份。"""

    # Abaqus 2021 的 session 没有 about 属性；uti.getVersion() 实测返回 2021。
    import uti

    return _to_text(uti.getVersion())


def _repository_names(repository, warning_code, warnings):
    """读取 repository 键名；失败时只记录固定代码，不记录异常原文。"""

    try:
        raw_names = list(repository.keys())
    except Exception:
        warnings.append(warning_code)
        return [], False

    names = []
    truncated = len(raw_names) > MAX_NAMES_PER_FIELD
    for raw_name in raw_names[:MAX_NAMES_PER_FIELD]:
        name = _to_text(raw_name)
        if name:
            names.append(name)
    names.sort()
    return names, truncated


def _model_payload(model_name, model, warnings):
    """只提取当前模型内允许公开的对象名称。"""

    parts, parts_cut = _repository_names(
        model.parts, "PARTS_UNREADABLE", warnings
    )
    materials, materials_cut = _repository_names(
        model.materials, "MATERIALS_UNREADABLE", warnings
    )
    steps, steps_cut = _repository_names(
        model.steps, "STEPS_UNREADABLE", warnings
    )
    instances, instances_cut = _repository_names(
        model.rootAssembly.instances, "INSTANCES_UNREADABLE", warnings
    )
    loads, loads_cut = _repository_names(
        model.loads, "LOADS_UNREADABLE", warnings
    )
    conditions, conditions_cut = _repository_names(
        model.boundaryConditions, "BCS_UNREADABLE", warnings
    )
    interactions, interactions_cut = _repository_names(
        model.interactions, "INTERACTIONS_UNREADABLE", warnings
    )
    return {
        "name": _to_text(model_name),
        "parts": parts,
        "materials": materials,
        "steps": steps,
        "instances": instances,
        "loads": loads,
        "boundary_conditions": conditions,
        "interactions": interactions,
    }, any(
        (
            parts_cut,
            materials_cut,
            steps_cut,
            instances_cut,
            loads_cut,
            conditions_cut,
            interactions_cut,
        )
    )


def _collect_snapshot(mdb_object):
    """从当前 MDB 构造不含路径、数值和网格的白名单字典。"""

    warnings = []
    truncated = False
    models = []
    try:
        raw_model_names = list(mdb_object.models.keys())
    except Exception:
        raw_model_names = []
        warnings.append("MODELS_UNREADABLE")

    if len(raw_model_names) > MAX_MODELS:
        truncated = True
    model_pairs = []
    for raw_name in raw_model_names[:MAX_MODELS]:
        model_pairs.append((_to_text(raw_name), raw_name))
    model_pairs.sort(key=lambda item: item[0])

    for display_name, raw_name in model_pairs:
        try:
            model = mdb_object.models[raw_name]
            model_data, model_cut = _model_payload(
                display_name, model, warnings
            )
            models.append(model_data)
            truncated = truncated or model_cut
        except Exception:
            # 单个模型异常时继续读取其他模型，且不写出异常文本。
            warnings.append("MODEL_UNREADABLE")

    generated_at = time.time()
    whole_seconds = int(generated_at)
    microseconds = int((generated_at - whole_seconds) * 1000000)
    utc_time = time.gmtime(whole_seconds)
    timestamp = "%s%06dZ" % (
        time.strftime("%Y%m%dT%H%M%S", utc_time),
        microseconds,
    )
    snapshot_id = "%s_%s_%s" % (
        timestamp,
        os.getpid(),
        uuid.uuid4().hex,
    )
    return {
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "target_release": TARGET_RELEASE,
        "complete": True,
        "snapshot_id": snapshot_id,
        "generated_at_utc": "%s.%06dZ" % (
            time.strftime("%Y-%m-%dT%H:%M:%S", utc_time),
            microseconds,
        ),
        "producer_pid": os.getpid(),
        "truncated": bool(truncated),
        "warnings": sorted(set(warnings)),
        "models": models,
    }


def _snapshot_directory():
    """返回 Windows 当前用户的固定本地快照目录。"""

    local_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_data:
        base_directory = local_data
    else:
        base_directory = os.path.expanduser("~")
    return os.path.join(
        base_directory,
        "AbaqusCodexAssistant",
        "readonly_snapshots",
    )


def _ensure_directory(directory):
    """兼容 Python 2.7 地创建固定目录，并处理并发创建。"""

    if os.path.isdir(directory):
        return
    try:
        os.makedirs(directory)
    except OSError:
        if not os.path.isdir(directory):
            raise


def _write_snapshot(payload, directory):
    """先写唯一临时文件，再在同目录原子改名为最终 JSON。"""

    _ensure_directory(directory)
    snapshot_id = payload["snapshot_id"]
    final_path = os.path.join(directory, "snapshot_%s.json" % snapshot_id)
    temporary_path = os.path.join(directory, "snapshot_%s.tmp" % snapshot_id)
    serialized = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    if not isinstance(serialized, bytes):
        serialized = serialized.encode("ascii")
    if len(serialized) > MAX_SNAPSHOT_BYTES:
        raise ValueError("snapshot exceeds safe size limit")

    try:
        with io.open(temporary_path, "wb") as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        # 最终名称含随机 UUID，不覆盖任何已有文件，兼容 Windows Python 2.7。
        os.rename(temporary_path, final_path)
    except Exception:
        try:
            if os.path.isfile(temporary_path):
                os.remove(temporary_path)
        except Exception:
            pass
        raise
    return final_path


def write_readonly_snapshot():
    """由菜单调用一次：读取当前 MDB、写快照并立即返回。"""

    try:
        # 延后导入可确保菜单显示本身不访问当前模型。
        from abaqus import mdb
    except Exception:
        print("Abaqus Codex: snapshot failed [IMPORT_FAILED]; model unchanged.")
        return False

    try:
        # 只在用户点击时检查 Kernel 版本；识别失败时安全停止。
        running_release = _running_release()
    except Exception:
        print(
            "Abaqus Codex: snapshot failed [VERSION_CHECK_FAILED]; "
            "model unchanged."
        )
        return False
    if running_release != TARGET_RELEASE:
        print("Abaqus Codex: snapshot requires Abaqus 2021 [WRONG_VERSION].")
        return False

    try:
        payload = _collect_snapshot(mdb)
    except Exception:
        print("Abaqus Codex: snapshot failed [COLLECT_FAILED]; model unchanged.")
        return False

    try:
        _write_snapshot(payload, _snapshot_directory())
    except Exception:
        # 固定阶段码便于排查，同时不泄露路径、模型名或异常原文。
        print("Abaqus Codex: snapshot failed [WRITE_FAILED]; model unchanged.")
        return False

    print("Abaqus Codex: read-only model snapshot updated.")
    return True


__all__ = ["write_readonly_snapshot"]
