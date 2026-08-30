# -*- coding: utf-8 -*-
"""把 Abaqus 2021 安全材料动作插件安装到用户插件目录。"""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from abaqus_codex.abqpy_environment import parse_release_year
from abaqus_codex.environment import inspect_abaqus
from abaqus_codex.paths import resource_root, user_data_root


# 第一版只面向维护者已经真机验证的 Abaqus 2021。
SUPPORTED_ABAQUS_YEAR = 2021
PLUGIN_DIRECTORY_NAME = "safe_material_action"
REQUIRED_PLUGIN_FILES = frozenset(
    {
        "safe_material_action_plugin.py",
        "safe_material_action_kernel.py",
    }
)


class SafeActionSetupError(RuntimeError):
    """表示安全动作插件没有完成预检或安装。"""


def _lexical_absolute(path: Path) -> Path:
    """不解析 symlink/junction 地转为绝对路径。"""

    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _is_reparse_point(path: Path) -> bool:
    try:
        if path.is_symlink():
            return True
    except OSError:
        return True
    is_junction = getattr(path, "is_junction", None)
    if callable(is_junction):
        try:
            if is_junction():
                return True
        except OSError:
            return True
    try:
        attributes = int(getattr(path.lstat(), "st_file_attributes", 0) or 0)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return bool(attributes & 0x0400)


def _assert_no_reparse_path(path: Path, label: str) -> None:
    current = _lexical_absolute(path)
    while True:
        if _is_reparse_point(current):
            raise SafeActionSetupError(
                "{0}包含符号链接或 Windows 联接点：{1}".format(label, current)
            )
        if current.parent == current:
            return
        current = current.parent


def _nearest_existing_path(path: Path) -> Path:
    current = _lexical_absolute(path)
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def _same_storage_volume(left: Path, right: Path) -> bool:
    left_drive = os.path.normcase(os.path.splitdrive(str(_lexical_absolute(left)))[0])
    right_drive = os.path.normcase(os.path.splitdrive(str(_lexical_absolute(right)))[0])
    if left_drive or right_drive:
        return bool(left_drive and left_drive == right_drive)
    try:
        return _nearest_existing_path(left).stat().st_dev == _nearest_existing_path(right).stat().st_dev
    except OSError:
        return False


def default_plugin_source() -> Path:
    """返回安装资源内随项目维护的插件目录。"""

    return resource_root() / "abaqus_plugins" / PLUGIN_DIRECTORY_NAME


def default_plugin_target() -> Path:
    """返回当前用户的 Abaqus 插件安装目录。"""

    # Windows 优先使用 USERPROFILE；其他环境和测试可退回 Path.home()。
    user_profile = os.environ.get("USERPROFILE", "").strip()
    home = Path(user_profile) if user_profile else Path.home()
    return home / "abaqus_plugins" / PLUGIN_DIRECTORY_NAME


def _file_digest(path: Path) -> str:
    """分块计算文件摘要，避免把整个插件文件一次读入内存。"""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _directory_manifest(root: Path) -> Dict[str, str]:
    """生成不跟随符号链接的目录清单，用于判断两份插件是否相同。"""

    if _is_reparse_point(root):
        raise SafeActionSetupError(
            "插件目录不能是符号链接或 Windows 联接点：{0}".format(root)
        )
    if not root.is_dir():
        raise SafeActionSetupError("没有找到有效的插件目录：{0}".format(root))

    manifest: Dict[str, str] = {}
    def visit(directory: Path) -> None:
        try:
            with os.scandir(directory) as scan:
                children = sorted(scan, key=lambda item: item.name)
        except OSError as error:
            raise SafeActionSetupError(
                "无法安全读取插件目录：{0}".format(directory)
            ) from error
        for child in children:
            path = directory / child.name
            relative = path.relative_to(root).as_posix()
            if _is_reparse_point(path):
                raise SafeActionSetupError(
                    "插件目录中含有符号链接或 Windows 联接点，"
                    "已停止安装：{0}".format(relative)
                )
            if child.is_dir(follow_symlinks=False):
                manifest["目录:{0}".format(relative)] = ""
                visit(path)
            elif child.is_file(follow_symlinks=False):
                manifest["文件:{0}".format(relative)] = _file_digest(path)
            else:
                raise SafeActionSetupError(
                    "插件目录中含有不支持的文件类型：{0}".format(relative)
                )

    visit(root)
    return manifest


def _validate_source(source: Path) -> Dict[str, str]:
    """确认源码完整，并返回之后可复用的内容清单。"""

    manifest = _directory_manifest(source)
    missing = [name for name in REQUIRED_PLUGIN_FILES if not (source / name).is_file()]
    if missing:
        raise SafeActionSetupError(
            "插件源码不完整，缺少：{0}".format("、".join(sorted(missing)))
        )
    return manifest


def _next_backup_path(target: Path, backup_root: Path) -> Path:
    """在用户数据恢复区生成备份，避免 Abaqus 重复扫描。"""

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = backup_root / "{0}.backup-{1}".format(target.name, timestamp)
    if not base.exists() and not base.is_symlink():
        return base

    # 同一秒内多次安装时增加序号，任何已有备份都不会被覆盖。
    for index in range(1, 1000):
        candidate = backup_root / "{0}.backup-{1}-{2:03d}".format(
            target.name, timestamp, index
        )
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise SafeActionSetupError("同名备份过多，请先人工整理插件目录。")


def _next_recovery_path(target: Path, backup_root: Path, label: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = backup_root / "{0}.{1}-{2}".format(target.name, label, timestamp)
    if not base.exists() and not base.is_symlink():
        return base
    for index in range(1, 1000):
        candidate = backup_root / "{0}-{1:03d}".format(base.name, index)
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise SafeActionSetupError("同名恢复副本过多，请先人工整理。")


def _new_staging_path(target: Path) -> Path:
    """生成目标旁边的临时安装目录，复制完成后再整体换入。"""

    for _unused in range(20):
        candidate = target.with_name(
            ".{0}.installing-{1}".format(target.name, uuid.uuid4().hex[:12])
        )
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise SafeActionSetupError("无法生成唯一的临时安装目录。")


def _preflight_abaqus_2021() -> Dict[str, object]:
    """只允许在检测到可用 Abaqus 2021 时形成安装计划。"""

    result = inspect_abaqus()
    if not result.get("usable"):
        raise SafeActionSetupError(
            "没有检测到可用的 Abaqus 及其内置 Python，未安装插件。"
        )
    if parse_release_year(result.get("version")) != SUPPORTED_ABAQUS_YEAR:
        raise SafeActionSetupError(
            "当前插件第一版只支持 Abaqus 2021；检测到版本：{0}。".format(
                result.get("version") or "无法识别"
            )
        )
    return result


def setup_safe_action_plugin(
    confirmed: bool,
    target: Optional[Path] = None,
    source: Optional[Path] = None,
    backup_root: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, object]:
    """预检并安装插件；dry-run 只返回计划，不创建任何文件。"""

    if not confirmed and not dry_run:
        raise SafeActionSetupError(
            "安装会写入用户 Abaqus 插件目录；请明确确认或先使用 dry-run。"
        )

    abaqus = _preflight_abaqus_2021()
    source_path = Path(source) if source is not None else default_plugin_source()
    target_path = Path(target) if target is not None else default_plugin_target()
    backup_root_path = (
        Path(backup_root)
        if backup_root is not None
        else user_data_root() / "recovery" / "plugin"
    )

    source_path = _lexical_absolute(source_path)
    target_path = _lexical_absolute(target_path)
    backup_root_path = _lexical_absolute(backup_root_path)
    _assert_no_reparse_path(source_path, "插件资源路径")
    _assert_no_reparse_path(target_path, "插件安装路径")
    _assert_no_reparse_path(backup_root_path, "插件恢复路径")
    if (
        source_path == target_path
        or source_path in target_path.parents
        or target_path in source_path.parents
    ):
        raise SafeActionSetupError(
            "插件资源和安装目录不能相同、互为父目录或子目录。"
        )
    if target_path.parent in backup_root_path.parents or backup_root_path == target_path.parent:
        raise SafeActionSetupError("插件恢复区不能位于 Abaqus 插件扫描目录内。")
    if not _same_storage_volume(target_path.parent, backup_root_path):
        raise SafeActionSetupError(
            "插件目标和恢复区不在同一磁盘；已在复制前停止。"
        )

    source_manifest = _validate_source(source_path)
    target_exists = target_path.exists()
    if target_exists and not target_path.is_dir():
        raise SafeActionSetupError(
            "插件目标已存在且不是目录；为保证可完整恢复，未更改该文件。"
        )
    target_matches = False
    if target_exists and target_path.is_dir():
        target_matches = _directory_manifest(target_path) == source_manifest

    if target_matches:
        return {
            "changed": False,
            "dry_run": dry_run,
            "source": str(source_path),
            "target": str(target_path),
            "backup": None,
            "abaqus": abaqus,
            "message": "安全动作插件已是当前版本，未重复安装。",
        }

    backup_path = (
        _next_backup_path(target_path, backup_root_path) if target_exists else None
    )
    if dry_run:
        message = (
            "演练完成：现有插件将先备份，再安装项目版本。"
            if target_exists
            else "演练完成：将新安装安全动作插件。"
        )
        return {
            "changed": True,
            "dry_run": True,
            "source": str(source_path),
            "target": str(target_path),
            "backup": str(backup_path) if backup_path is not None else None,
            "abaqus": abaqus,
            "message": message,
        }

    staging_path = _new_staging_path(target_path)
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_exists:
            backup_root_path.mkdir(parents=True, exist_ok=True)
        _assert_no_reparse_path(target_path.parent, "插件安装父路径")
        if target_exists:
            _assert_no_reparse_path(backup_root_path, "插件恢复路径")
        # 先完整复制到同级临时目录，复制失败时不碰原插件。
        shutil.copytree(source_path, staging_path, copy_function=shutil.copy2)
        if _directory_manifest(staging_path) != source_manifest:
            raise SafeActionSetupError("临时插件副本校验失败，原插件未更改。")
    except (OSError, shutil.Error, SafeActionSetupError) as error:
        if staging_path.exists() and not staging_path.is_symlink():
            try:
                backup_root_path.mkdir(parents=True, exist_ok=True)
                staging_path.replace(
                    _next_recovery_path(target_path, backup_root_path, "failed-copy")
                )
            except (OSError, SafeActionSetupError):
                pass
        raise SafeActionSetupError(
            "复制插件失败，原插件未更改：{0}".format(error)
        ) from error

    original_was_backed_up = False
    try:
        if target_exists:
            assert backup_path is not None
            _assert_no_reparse_path(target_path, "插件安装路径")
            target_path.replace(backup_path)
            original_was_backed_up = True
        staging_path.replace(target_path)
    except OSError as error:
        # 若新插件尚未换入，尽力把已备份的原目录恢复到原位置。
        if (
            original_was_backed_up
            and backup_path is not None
            and not target_path.exists()
        ):
            try:
                backup_path.replace(target_path)
            except (OSError, SafeActionSetupError):
                pass
        if staging_path.exists() and not staging_path.is_symlink():
            try:
                backup_root_path.mkdir(parents=True, exist_ok=True)
                staging_path.replace(
                    _next_recovery_path(target_path, backup_root_path, "failed-switch")
                )
            except (OSError, SafeActionSetupError):
                pass
        raise SafeActionSetupError(
            "切换插件目录失败；没有递归删除任何目录：{0}".format(error)
        ) from error

    return {
        "changed": True,
        "dry_run": False,
        "source": str(source_path),
        "target": str(target_path),
        "backup": str(backup_path) if backup_path is not None else None,
        "abaqus": abaqus,
        "message": (
            "已备份旧插件并安装 Abaqus 2021 安全动作插件。"
            if backup_path is not None
            else "已安装 Abaqus 2021 安全动作插件。"
        ),
    }
