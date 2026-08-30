# -*- coding: utf-8 -*-
"""安装版对 Codex Skill 和已验证 Abaqus 插件的用户级集成。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Mapping, Optional

from abaqus_codex import __version__
from abaqus_codex.abqpy_environment import parse_release_year
from abaqus_codex.environment import inspect_abaqus
from abaqus_codex.paths import resource_root, user_data_root
from abaqus_codex.safe_action_setup import (
    PLUGIN_DIRECTORY_NAME,
    SUPPORTED_ABAQUS_YEAR,
    SafeActionSetupError,
    default_plugin_target,
    setup_safe_action_plugin,
)


PRODUCT_NAME = "abaqus-codex-assistant"
SKILL_DIRECTORY_NAME = "abaqus-modeling-guide"
MANIFEST_FILENAME = "integration-manifest.json"
MANIFEST_SCHEMA_VERSION = 1
WINDOWS_REPARSE_POINT = 0x0400


class DistributionIntegrationError(RuntimeError):
    """发布版用户集成不能安全完成。"""


def _lexical_absolute(path: Path) -> Path:
    """返回不解析符号链接或 junction 的绝对路径。"""

    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _lexical_paths_equal(left: object, right: Path) -> bool:
    """按当前平台的路径语义比较，不解析 symlink 或 junction。"""

    left_text = str(left or "").strip()
    if not left_text:
        return False
    left_key = os.path.normcase(os.fspath(_lexical_absolute(Path(left_text))))
    right_key = os.path.normcase(os.fspath(_lexical_absolute(right)))
    return left_key == right_key


def _is_reparse_point(path: Path) -> bool:
    """不跟随目标地检查 symlink、Windows junction 及其他重解析点。"""

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
        stat_result = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        # 无法安全识别的现有路径一律失败关闭。
        return True
    attributes = int(getattr(stat_result, "st_file_attributes", 0) or 0)
    return bool(attributes & WINDOWS_REPARSE_POINT)


def _assert_no_reparse_path(path: Path, *, label: str) -> None:
    """检查目标和所有现有父路径，避免安装/卸载越界。"""

    current = _lexical_absolute(path)
    while True:
        if _is_reparse_point(current):
            raise DistributionIntegrationError(
                "{0}包含符号链接或 Windows 联接点，未更改文件：{1}".format(
                    label, current
                )
            )
        parent = current.parent
        if parent == current:
            break
        current = parent


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _directory_manifest(root: Path) -> Dict[str, str]:
    """读取不跟随符号链接的完整目录指纹。"""

    if _is_reparse_point(root):
        raise DistributionIntegrationError(
            "受管目录不能是符号链接或 Windows 联接点：{0}".format(root)
        )
    if not root.is_dir():
        raise DistributionIntegrationError("没有找到完整目录：{0}".format(root))
    entries: Dict[str, str] = {}

    def visit(directory: Path) -> None:
        try:
            with os.scandir(directory) as scan:
                children = sorted(scan, key=lambda item: item.name)
        except OSError as error:
            raise DistributionIntegrationError(
                "无法安全读取受管目录：{0}".format(directory)
            ) from error
        for child in children:
            path = directory / child.name
            relative = path.relative_to(root).as_posix()
            if _is_reparse_point(path):
                raise DistributionIntegrationError(
                    "目录中含有符号链接或 Windows 联接点，已停止：{0}".format(
                        relative
                    )
                )
            if child.is_dir(follow_symlinks=False):
                entries["目录:" + relative] = ""
                visit(path)
            elif child.is_file(follow_symlinks=False):
                entries["文件:" + relative] = _digest_file(path)
            else:
                raise DistributionIntegrationError(
                    "目录中含有不支持的文件类型：{0}".format(relative)
                )

    visit(root)
    return entries


def _directory_digest(root: Path) -> str:
    payload = json.dumps(
        _directory_manifest(root),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _next_recovery_path(recovery_root: Path, target: Path, label: str) -> Path:
    """在用户数据恢复区中生成唯一路径，避免被 Codex/Abaqus 扫描。"""

    recovery_root = _lexical_absolute(recovery_root)
    _assert_no_reparse_path(recovery_root, label="用户恢复路径")
    base = recovery_root / "{0}.{1}-{2}".format(target.name, label, _timestamp())
    if not base.exists() and not base.is_symlink():
        return base
    for index in range(1, 1000):
        candidate = recovery_root / "{0}-{1:03d}".format(base.name, index)
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise DistributionIntegrationError("同名恢复副本过多，请先人工整理：{0}".format(recovery_root))


def _move_directory(source: Path, destination: Path) -> None:
    """仅使用同卷原子改名；绝不用复制后递归删除来伪装移动。"""

    source = _lexical_absolute(source)
    destination = _lexical_absolute(destination)
    _assert_no_reparse_path(source, label="待移动目录")
    _assert_no_reparse_path(destination, label="恢复目标路径")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_reparse_path(destination.parent, label="恢复目标父路径")
    try:
        source.replace(destination)
    except OSError as error:
        raise DistributionIntegrationError(
            "无法将目录原子移入用户恢复区；"
            "请确保 CODEX_HOME、Abaqus 插件目录和 LOCALAPPDATA 位于同一磁盘。"
        ) from error


def _nearest_existing_path(path: Path) -> Path:
    current = _lexical_absolute(path)
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def _same_storage_volume(left: Path, right: Path) -> bool:
    """在任何复制前判断目标与恢复区能否用原子改名往返。"""

    left = _lexical_absolute(left)
    right = _lexical_absolute(right)
    left_drive = os.path.normcase(os.path.splitdrive(str(left))[0])
    right_drive = os.path.normcase(os.path.splitdrive(str(right))[0])
    if left_drive or right_drive:
        return bool(left_drive and left_drive == right_drive)
    try:
        return _nearest_existing_path(left).stat().st_dev == _nearest_existing_path(right).stat().st_dev
    except OSError:
        return False


def _staging_path(target: Path) -> Path:
    for _unused in range(20):
        candidate = target.with_name(
            ".{0}.installing-{1}".format(target.name, uuid.uuid4().hex[:12])
        )
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise DistributionIntegrationError("无法创建唯一的临时安装目录。")


def _install_directory(
    source: Path,
    target: Path,
    *,
    recovery_root: Path,
    dry_run: bool,
) -> Dict[str, object]:
    """先校验、再复制、最后整体换入，且始终保留旧目录。"""

    source = _lexical_absolute(source)
    target = _lexical_absolute(target)
    recovery_root = _lexical_absolute(recovery_root)
    _assert_no_reparse_path(source, label="集成资源路径")
    _assert_no_reparse_path(target, label="集成目标路径")
    _assert_no_reparse_path(recovery_root, label="用户恢复路径")
    if not source.is_dir():
        raise DistributionIntegrationError("没有找到完整目录：{0}".format(source))
    if (
        source == target
        or source in target.parents
        or target in source.parents
        or recovery_root == target.parent
        or target.parent in recovery_root.parents
    ):
        raise DistributionIntegrationError(
            "集成资源、目标和恢复区不能相互重叠，"
            "恢复区也不能位于 Codex/Abaqus 扫描目录内。"
        )
    if not _same_storage_volume(target.parent, recovery_root):
        raise DistributionIntegrationError(
            "集成目标与用户恢复区不在同一磁盘；"
            "为保证可原子恢复，已在复制前停止。"
        )

    source_digest = _directory_digest(source)
    target_exists = target.exists()
    if target_exists and not target.is_dir():
        raise DistributionIntegrationError("集成目标已存在且不是目录：{0}".format(target))
    if target_exists and _directory_digest(target) == source_digest:
        return {
            "changed": False,
            "source": str(source),
            "target": str(target),
            "backup": None,
            "recovery_root": str(recovery_root),
            "installed_digest": source_digest,
        }

    backup = (
        _next_recovery_path(recovery_root, target, "backup")
        if target_exists
        else None
    )
    if dry_run:
        return {
            "changed": True,
            "source": str(source),
            "target": str(target),
            "backup": str(backup) if backup is not None else None,
            "recovery_root": str(recovery_root),
            "installed_digest": source_digest,
        }

    stage = _staging_path(target)
    try:
        _assert_no_reparse_path(target, label="集成目标路径")
        target.parent.mkdir(parents=True, exist_ok=True)
        _assert_no_reparse_path(target.parent, label="集成目标父路径")
        shutil.copytree(source, stage, copy_function=shutil.copy2)
        if _directory_digest(stage) != source_digest:
            raise DistributionIntegrationError("临时集成副本校验失败。")
    except (OSError, shutil.Error, DistributionIntegrationError) as error:
        # 不递归删除失败副本；改名后供诊断和恢复。
        if stage.exists() and not stage.is_symlink():
            try:
                failed_copy = _next_recovery_path(recovery_root, target, "failed-copy")
                _move_directory(stage, failed_copy)
            except (OSError, DistributionIntegrationError):
                pass
        raise DistributionIntegrationError("复制集成资源失败，原目录未更改。") from error

    backed_up = False
    try:
        _assert_no_reparse_path(target, label="集成目标路径")
        if backup is not None:
            _move_directory(target, backup)
            backed_up = True
        stage.replace(target)
    except (OSError, DistributionIntegrationError) as error:
        if backed_up and backup is not None and not target.exists():
            try:
                _move_directory(backup, target)
            except (OSError, DistributionIntegrationError):
                pass
        if stage.exists() and not stage.is_symlink():
            try:
                failed_switch = _next_recovery_path(
                    recovery_root, target, "failed-switch"
                )
                _move_directory(stage, failed_switch)
            except (OSError, DistributionIntegrationError):
                pass
        raise DistributionIntegrationError(
            "切换集成目录失败；没有递归删除任何用户目录。"
        ) from error

    return {
        "changed": True,
        "source": str(source),
        "target": str(target),
        "backup": str(backup) if backup is not None else None,
        "recovery_root": str(recovery_root),
        "installed_digest": source_digest,
    }


def _manifest_path(data_root: Optional[Path]) -> Path:
    selected = _lexical_absolute(Path(data_root) if data_root is not None else user_data_root())
    return selected / MANIFEST_FILENAME


def _selected_codex_home(explicit: Optional[Path]) -> Path:
    """选择 CODEX_HOME，但不在安全检查前解析链接/junction。"""

    if explicit is not None and str(explicit).strip():
        return _lexical_absolute(explicit)
    environment_value = os.environ.get("CODEX_HOME", "").strip()
    if environment_value:
        return _lexical_absolute(Path(environment_value))
    user_profile = os.environ.get("USERPROFILE", "").strip()
    home = Path(user_profile) if user_profile else Path.home()
    return _lexical_absolute(home / ".codex")


def _read_manifest(path: Path, *, required: bool) -> Optional[dict[str, object]]:
    _assert_no_reparse_path(path, label="用户集成清单路径")
    if not path.is_file():
        if required:
            raise DistributionIntegrationError("未找到用户集成清单，未更改任何文件。")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as error:
        raise DistributionIntegrationError("用户集成清单已损坏，未更改任何文件。") from error
    if (
        not isinstance(payload, dict)
        or payload.get("product") != PRODUCT_NAME
        or payload.get("schema_version") != MANIFEST_SCHEMA_VERSION
    ):
        raise DistributionIntegrationError("用户集成清单不受支持，未更改任何文件。")
    return payload


def _write_manifest(path: Path, payload: Mapping[str, object]) -> None:
    _assert_no_reparse_path(path, label="用户集成清单路径")
    path.parent.mkdir(parents=True, exist_ok=True)
    _assert_no_reparse_path(path.parent, label="用户集成清单父路径")
    stage = path.with_name(".{0}.writing-{1}".format(path.name, uuid.uuid4().hex[:12]))
    try:
        stage.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        stage.replace(path)
    except OSError as error:
        if stage.exists():
            try:
                failed_write = _next_recovery_path(
                    path.parent / "recovery" / "manifest", path, "failed-write"
                )
                _move_directory(stage, failed_write)
            except (OSError, DistributionIntegrationError):
                pass
        raise DistributionIntegrationError("无法写入用户集成清单。") from error


def _prior_component(
    manifest: Optional[Mapping[str, object]], name: str, target: Path
) -> Mapping[str, object]:
    if not isinstance(manifest, Mapping):
        return {}
    component = manifest.get(name)
    if not isinstance(component, Mapping):
        return {}
    if not _lexical_paths_equal(component.get("target"), target):
        return {}
    return component


def _validate_prior_manifest_targets(
    manifest: Mapping[str, object],
    *,
    manifest_path: Path,
    selected_codex_home: Path,
    skill_target: Path,
    plugin_target: Path,
) -> None:
    """不允许新的 CODEX_HOME/用户目标覆盖尚未移除的旧集成清单。"""

    recorded_data = _lexical_absolute(Path(str(manifest.get("user_data_root") or "")))
    recorded_codex = _lexical_absolute(Path(str(manifest.get("codex_home") or "")))
    prior_skill = manifest.get("skill")
    prior_plugin = manifest.get("plugin")
    recorded_skill = (
        _lexical_absolute(Path(str(prior_skill.get("target") or "")))
        if isinstance(prior_skill, Mapping)
        else None
    )
    recorded_plugin = (
        _lexical_absolute(Path(str(prior_plugin.get("target") or "")))
        if isinstance(prior_plugin, Mapping)
        else None
    )
    if (
        recorded_data != manifest_path.parent
        or recorded_codex != selected_codex_home
        or recorded_skill != skill_target
        or recorded_plugin != plugin_target
    ):
        raise DistributionIntegrationError(
            "已有集成清单属于另一个 CODEX_HOME 或用户目标；"
            "请先使用原配置运行 integration-remove，再重新安装。"
        )
    for name, component in (("skill", prior_skill), ("plugin", prior_plugin)):
        if not isinstance(component, Mapping) or not bool(component.get("managed")):
            continue
        recovery_text = str(component.get("recovery_root") or "").strip()
        expected_recovery = manifest_path.parent / "recovery" / name
        if not recovery_text or _lexical_absolute(Path(recovery_text)) != expected_recovery:
            raise DistributionIntegrationError(
                "历史集成清单使用了扫描目录旁的旧备份；"
                "本版不会自动迁移或删除，请先人工确认。"
            )


def _component_with_ownership(
    result: Mapping[str, object],
    prior: Mapping[str, object],
    *,
    preserve_initial_backup: bool = False,
) -> dict[str, object]:
    component = dict(result)
    changed = bool(component.get("changed"))
    component["managed"] = changed or bool(prior.get("managed"))
    prior_recoveries = prior.get("upgrade_recoveries")
    recoveries = (
        [str(item) for item in prior_recoveries if str(item).strip()]
        if isinstance(prior_recoveries, list)
        else []
    )
    if not changed:
        component["backup"] = prior.get("backup")
        component["recovery_root"] = (
            prior.get("recovery_root") or component.get("recovery_root")
        )
    elif preserve_initial_backup:
        new_upgrade_recovery = component.get("backup")
        if new_upgrade_recovery:
            recoveries.append(str(new_upgrade_recovery))
        component["backup"] = prior.get("backup")
    component["upgrade_recoveries"] = recoveries
    return component


def _prior_managed_target_is_unchanged(
    prior: Mapping[str, object], target: Path
) -> bool:
    """判断当前目标是上一版受管副本，而不是用户新内容。"""

    if not bool(prior.get("managed")):
        return False
    if not _lexical_paths_equal(prior.get("target"), target):
        return False
    expected = str(prior.get("installed_digest") or "")
    if not expected or not target.is_dir():
        return False
    _assert_no_reparse_path(target, label="已安装集成目标")
    return _directory_digest(target) == expected


def _mark_upgrade_recovery(
    result: Mapping[str, object],
    *,
    target: Path,
    recovery_root: Path,
    dry_run: bool,
) -> dict[str, object]:
    """把已受管的旧程序版标记为升级恢复，不替代首次用户备份。"""

    updated = dict(result)
    backup_text = str(updated.get("backup") or "").strip()
    if not bool(updated.get("changed")) or not backup_text:
        return updated
    backup = _lexical_absolute(Path(backup_text))
    upgrade = _next_recovery_path(recovery_root, target, "upgrade")
    if not dry_run:
        _move_directory(backup, upgrade)
    updated["backup"] = str(upgrade)
    return updated


def _rollback_install(component: Mapping[str, object]) -> None:
    """尽力撤回本轮换入；失败副本仍以可恢复改名保留。"""

    if not bool(component.get("changed")):
        return
    target_text = str(component.get("target") or "").strip()
    if not target_text:
        return
    target = _lexical_absolute(Path(target_text))
    recovery_root = _component_recovery_root(component, target)
    recoveries = component.get("upgrade_recoveries")
    if isinstance(recoveries, list) and recoveries:
        backup = _valid_backup(
            target, recoveries[-1], recovery_root, label="upgrade"
        )
    else:
        backup = _valid_backup(
            target, component.get("backup"), recovery_root
        )
    installed_digest = str(component.get("installed_digest") or "")
    if target.is_dir() and not target.is_symlink():
        try:
            if installed_digest and _directory_digest(target) == installed_digest:
                failed_install = _next_recovery_path(
                    recovery_root, target, "failed-install"
                )
                _move_directory(target, failed_install)
        except (OSError, DistributionIntegrationError):
            return
    if backup is not None and backup.is_dir() and not target.exists():
        try:
            _move_directory(backup, target)
        except (OSError, DistributionIntegrationError):
            pass


def integration_setup(
    *,
    confirmed: bool,
    codex_home_path: Optional[Path] = None,
    data_root: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, object]:
    """安装 Skill，并仅对实时验证的 Abaqus 2021 安装安全插件。"""

    if not confirmed and not dry_run:
        raise DistributionIntegrationError(
            "集成会写入 Codex Skill 和可能的 Abaqus 用户插件目录；"
            "请明确确认。"
        )

    resources = resource_root()
    selected_codex_home = _selected_codex_home(codex_home_path)
    manifest_path = _manifest_path(data_root)
    prior_manifest = _read_manifest(manifest_path, required=False)
    skill_source = resources / "skills" / SKILL_DIRECTORY_NAME
    if not (skill_source / "SKILL.md").is_file():
        raise DistributionIntegrationError("Skill 资源不完整，缺少 SKILL.md。")
    selected_codex_home = _lexical_absolute(selected_codex_home)
    skill_target = _lexical_absolute(
        selected_codex_home / "skills" / SKILL_DIRECTORY_NAME
    )
    plugin_target = _lexical_absolute(default_plugin_target())
    if prior_manifest is not None:
        _validate_prior_manifest_targets(
            prior_manifest,
            manifest_path=manifest_path,
            selected_codex_home=selected_codex_home,
            skill_target=skill_target,
            plugin_target=plugin_target,
        )
    skill_recovery_root = manifest_path.parent / "recovery" / "skill"
    plugin_recovery_root = manifest_path.parent / "recovery" / "plugin"
    prior_skill = _prior_component(prior_manifest, "skill", skill_target)
    preserve_skill_backup = _prior_managed_target_is_unchanged(
        prior_skill, skill_target
    )
    skill_result = _install_directory(
        skill_source,
        skill_target,
        recovery_root=skill_recovery_root,
        dry_run=dry_run,
    )
    if preserve_skill_backup:
        skill_result = _mark_upgrade_recovery(
            skill_result,
            target=skill_target,
            recovery_root=skill_recovery_root,
            dry_run=dry_run,
        )
    skill = _component_with_ownership(
        skill_result,
        prior_skill,
        preserve_initial_backup=preserve_skill_backup,
    )

    abaqus = inspect_abaqus()
    year = parse_release_year(abaqus.get("version"))
    plugin_eligible = bool(
        abaqus.get("usable") and year == SUPPORTED_ABAQUS_YEAR
    )
    prior_plugin = _prior_component(prior_manifest, "plugin", plugin_target)
    preserve_plugin_backup = _prior_managed_target_is_unchanged(
        prior_plugin, plugin_target
    )
    plugin: dict[str, object] = {
        "eligible": plugin_eligible,
        "managed": bool(prior_plugin.get("managed")),
        "changed": False,
        "source": str(resources / "abaqus_plugins" / PLUGIN_DIRECTORY_NAME),
        "target": str(plugin_target),
        "backup": prior_plugin.get("backup"),
        "recovery_root": str(plugin_recovery_root),
        "upgrade_recoveries": prior_plugin.get("upgrade_recoveries") or [],
        "installed_digest": prior_plugin.get("installed_digest"),
        "message": (
            "已验证 Abaqus 2021，可安装安全插件。"
            if plugin_eligible
            else "未检测到已验证的 Abaqus 2021，已跳过安全插件。"
        ),
    }
    if plugin_eligible:
        if dry_run:
            plugin_result = setup_safe_action_plugin(
                confirmed=False,
                dry_run=True,
                source=resources / "abaqus_plugins" / PLUGIN_DIRECTORY_NAME,
                target=plugin_target,
                backup_root=plugin_recovery_root,
            )
        else:
            try:
                plugin_result = setup_safe_action_plugin(
                    confirmed=True,
                    source=resources / "abaqus_plugins" / PLUGIN_DIRECTORY_NAME,
                    target=plugin_target,
                    backup_root=plugin_recovery_root,
                )
            except SafeActionSetupError as error:
                _rollback_install(skill)
                raise DistributionIntegrationError(
                    "Abaqus 2021 安全插件未安装：{0}".format(error)
                ) from error
        plugin_digest = (
            _directory_digest(plugin_target)
            if not dry_run and plugin_target.is_dir()
            else _directory_digest(resources / "abaqus_plugins" / PLUGIN_DIRECTORY_NAME)
        )
        normalized_plugin = {
            "eligible": True,
            "changed": bool(plugin_result.get("changed")),
            "source": str(plugin_result.get("source")),
            "target": str(plugin_result.get("target")),
            "backup": plugin_result.get("backup"),
            "recovery_root": str(plugin_recovery_root),
            "installed_digest": plugin_digest,
            "message": str(plugin_result.get("message") or ""),
        }
        if preserve_plugin_backup:
            normalized_plugin = _mark_upgrade_recovery(
                normalized_plugin,
                target=plugin_target,
                recovery_root=plugin_recovery_root,
                dry_run=dry_run,
            )
        plugin = _component_with_ownership(
            normalized_plugin,
            prior_plugin,
            preserve_initial_backup=preserve_plugin_backup,
        )
        plugin["eligible"] = True
        plugin["message"] = normalized_plugin["message"]

    payload: Dict[str, object] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "product": PRODUCT_NAME,
        "version": __version__,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "resource_root": str(resources),
        "user_data_root": str(manifest_path.parent),
        "codex_home": str(selected_codex_home),
        "abaqus": {
            "usable": bool(abaqus.get("usable")),
            "version": str(abaqus.get("version") or ""),
            "release_year": year,
            "safe_plugin_verified": plugin_eligible,
        },
        "skill": skill,
        "plugin": plugin,
        "manifest_path": str(manifest_path),
        "dry_run": dry_run,
    }
    if not dry_run:
        try:
            _write_manifest(manifest_path, payload)
        except DistributionIntegrationError:
            _rollback_install(plugin)
            _rollback_install(skill)
            raise
    return payload


def _safe_component_from_manifest(
    manifest: Mapping[str, object], name: str, *, data_root_path: Path
) -> Mapping[str, object]:
    component = manifest.get(name)
    if not isinstance(component, Mapping):
        raise DistributionIntegrationError("集成清单缺少 {0} 组件。".format(name))
    target_text = str(component.get("target") or "").strip()
    if not target_text:
        raise DistributionIntegrationError("集成清单缺少 {0} 目标。".format(name))
    target = _lexical_absolute(Path(target_text))
    if name == "skill":
        recorded_codex = _lexical_absolute(Path(str(manifest.get("codex_home") or "")))
        expected = recorded_codex / "skills" / SKILL_DIRECTORY_NAME
    else:
        expected = _lexical_absolute(default_plugin_target())
    if target != expected:
        raise DistributionIntegrationError(
            "{0} 目标与清单所属用户不匹配，未更改文件。".format(name)
        )
    # 防止通过损坏清单把数据根或其父目录当成组件。
    if target == data_root_path or target in data_root_path.parents:
        raise DistributionIntegrationError("集成目标不能覆盖用户数据根。")
    _assert_no_reparse_path(target, label="{0} 受管目标".format(name))
    recovery_root = _component_recovery_root(component, target)
    expected_recovery = data_root_path / "recovery" / name
    if recovery_root != expected_recovery:
        raise DistributionIntegrationError(
            "{0} 恢复区与当前用户数据根不匹配。".format(name)
        )
    _valid_backup(target, component.get("backup"), recovery_root)
    recoveries = component.get("upgrade_recoveries")
    if recoveries is not None and not isinstance(recoveries, list):
        raise DistributionIntegrationError("集成清单的升级恢复记录格式无效。")
    for value in recoveries or []:
        _valid_backup(target, value, recovery_root, label="upgrade")
    return component


def _component_recovery_root(
    component: Mapping[str, object], target: Path
) -> Path:
    text = str(component.get("recovery_root") or "").strip()
    if not text:
        raise DistributionIntegrationError(
            "旧集成清单未记录隔离恢复区；"
            "为避免 Codex/Abaqus 重复加载，请先人工确认历史备份。"
        )
    recovery_root = _lexical_absolute(Path(text))
    _assert_no_reparse_path(recovery_root, label="用户恢复路径")
    if recovery_root == target.parent or target.parent in recovery_root.parents:
        raise DistributionIntegrationError(
            "恢复区不能位于 Codex/Abaqus 扫描目录内。"
        )
    return recovery_root


def _valid_backup(
    target: Path,
    value: object,
    recovery_root: Path,
    *,
    label: str = "backup",
) -> Optional[Path]:
    text = str(value or "").strip()
    if not text:
        return None
    backup = _lexical_absolute(Path(text))
    expected_prefix = target.name + ".{0}-".format(label)
    if backup.parent != recovery_root or not backup.name.startswith(expected_prefix):
        raise DistributionIntegrationError("恢复副本路径不安全，未更改文件。")
    _assert_no_reparse_path(backup, label="恢复副本路径")
    return backup


def _remove_component(component: Mapping[str, object]) -> Dict[str, object]:
    target = _lexical_absolute(Path(str(component["target"])))
    recovery_root = _component_recovery_root(component, target)
    backup = _valid_backup(target, component.get("backup"), recovery_root)
    result: Dict[str, object] = {
        "target": str(target),
        "backup": str(backup) if backup is not None else None,
        "status": "not_managed",
        "recovery_copy": None,
    }
    if not bool(component.get("managed")):
        return result
    installed_digest = str(component.get("installed_digest") or "")
    if target.exists():
        if not target.is_dir():
            result["status"] = "preserved_modified"
            return result
        try:
            unchanged = bool(installed_digest) and _directory_digest(target) == installed_digest
        except DistributionIntegrationError:
            unchanged = False
        if not unchanged:
            result["status"] = "preserved_modified"
            return result
        recovery = _next_recovery_path(recovery_root, target, "uninstalled")
        _move_directory(target, recovery)
        result["recovery_copy"] = str(recovery)
    if backup is not None and backup.exists():
        if backup.is_symlink() or not backup.is_dir() or target.exists():
            result["status"] = "preserved_backup"
            return result
        _move_directory(backup, target)
        result["status"] = "restored_backup"
    else:
        result["status"] = "moved_to_recovery" if result["recovery_copy"] else "already_absent"
    return result


def integration_remove(
    *, confirmed: bool, data_root: Optional[Path] = None
) -> Dict[str, object]:
    """可恢复地移除受管集成；用户改过的目录保持原位。"""

    if not confirmed:
        raise DistributionIntegrationError("移除集成前需要明确确认。")
    manifest_path = _manifest_path(data_root)
    manifest = _read_manifest(manifest_path, required=True)
    assert manifest is not None
    data_root_path = _lexical_absolute(manifest_path.parent)
    if _lexical_absolute(Path(str(manifest.get("user_data_root") or ""))) != data_root_path:
        raise DistributionIntegrationError("集成清单与当前用户数据根不匹配。")
    skill = _safe_component_from_manifest(manifest, "skill", data_root_path=data_root_path)
    plugin = _safe_component_from_manifest(manifest, "plugin", data_root_path=data_root_path)

    # 先完成所有清单/路径验证；再温和停止受管 MCP，
    # 最后才移动 Skill 和插件。
    plugin_target = _lexical_absolute(Path(str(plugin["target"])))
    mcp_home = plugin_target.parent.parent / ".abaqus-mcp"
    _assert_no_reparse_path(mcp_home, label="Abaqus MCP 用户目录")
    from abaqus_codex.mcp_setup import (
        remove_managed_codex_registration,
        stop_managed_headless_bridge_for_uninstall,
    )

    headless_bridge = stop_managed_headless_bridge_for_uninstall(target=mcp_home)
    headless_status = str(headless_bridge.get("status") or "")
    if headless_status == "stop_not_confirmed" or (
        headless_status == "stopped" and not bool(headless_bridge.get("stopped"))
    ):
        raise DistributionIntegrationError(
            "本项目管理的 MCP 后台进程尚未确认停止；"
            "已保留集成清单，请重试卸载或明确选择仅移除核心程序。"
        )

    mcp_registration = remove_managed_codex_registration(target=mcp_home)
    if str(mcp_registration.get("status") or "") == "remove_failed":
        raise DistributionIntegrationError(
            "本项目管理的 Codex MCP 注册未能移除；"
            "已保留集成清单，请重试卸载或明确选择仅移除核心程序。"
        )

    skill_result = _remove_component(skill)
    plugin_result = _remove_component(plugin)
    archived_manifest = _next_recovery_path(
        data_root_path / "recovery" / "manifest", manifest_path, "removed"
    )
    _move_directory(manifest_path, archived_manifest)
    return {
        "product": PRODUCT_NAME,
        "removed_at": datetime.now(timezone.utc).isoformat(),
        "manifest_path": str(manifest_path),
        "archived_manifest": str(archived_manifest),
        "skill": skill_result,
        "plugin": plugin_result,
        "headless_bridge": headless_bridge,
        "mcp_registration": mcp_registration,
    }


__all__ = [
    "DistributionIntegrationError",
    "MANIFEST_FILENAME",
    "integration_remove",
    "integration_setup",
]
