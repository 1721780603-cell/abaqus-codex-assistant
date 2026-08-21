# -*- coding: utf-8 -*-
"""检测 Abaqus MCP 的文件、Codex 注册和本地启动状态。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from abaqus_codex.mcp_guard import inspect_bridge_status


def vendor_python_paths(vendor_path: Path) -> List[Path]:
    """返回独立 vendor 及 pywin32 需要显式加入的子目录。"""

    candidates = [
        vendor_path,
        vendor_path / "win32",
        vendor_path / "win32" / "lib",
        vendor_path / "Pythonwin",
        vendor_path / "pywin32_system32",
    ]
    return [path for path in candidates if path.is_dir()]


def _decode_output(data: bytes) -> str:
    """将命令行输出转换为文本，并替换无法识别的字符。"""

    return data.decode("utf-8", errors="replace")


def _codex_candidates() -> List[Path]:
    """寻找可能可用的 Codex CLI，并保持候选顺序稳定。"""

    candidates: List[Path] = []
    path_command = shutil.which("codex")
    if path_command:
        candidates.append(Path(path_command))

    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            bin_root = Path(local_app_data) / "OpenAI" / "Codex" / "bin"
            if bin_root.is_dir():
                candidates.extend(
                    sorted(
                        bin_root.glob("*/codex.exe"),
                        key=lambda path: path.stat().st_mtime,
                        reverse=True,
                    )
                )

    # 同一个文件可能通过 PATH 和安装目录被找到两次，这里进行去重。
    unique_candidates: List[Path] = []
    seen = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key not in seen:
            seen.add(key)
            unique_candidates.append(candidate)
    return unique_candidates


def query_codex_mcp_list(timeout_seconds: int = 15) -> Tuple[Optional[Path], str]:
    """运行 codex mcp list，并返回实际可用的 CLI 路径和输出。"""

    errors: List[str] = []
    for candidate in _codex_candidates():
        try:
            completed = subprocess.run(
                [str(candidate), "mcp", "list"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            errors.append("{0}: {1}".format(candidate, error))
            continue

        output = _decode_output(completed.stdout)
        if completed.returncode == 0:
            return candidate, output
        errors.append("{0}: 退出码 {1}".format(candidate, completed.returncode))

    return None, "；".join(errors)


def parse_abaqus_mcp_names(output: str) -> List[str]:
    """从 codex mcp list 的表格文本中提取 Abaqus MCP 名称。"""

    names: List[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or "abaqus" not in stripped.lower():
            continue

        # 表格的第一列是服务器名称；只保留名称，避免输出环境变量等配置。
        name = stripped.split()[0]
        if name.lower() not in {"name", "名称"}:
            names.append(name)
    return names


def default_mcp_entry() -> Path:
    """返回本项目约定的 Abaqus MCP 默认入口路径。"""

    return Path.home() / ".abaqus-mcp" / "mcp_server.py"


def default_mcp_guard() -> Path:
    """返回项目管理的 MCP 防卡启动器默认路径。"""

    return Path.home() / ".abaqus-mcp" / "mcp_guard.py"


def verify_local_mcp_import(
    entry_file: Path, timeout_seconds: int = 15
) -> Tuple[bool, Optional[str], str]:
    """导入本地 MCP 入口，验证依赖是否可读取和加载。"""

    if not entry_file.is_file():
        return False, None, "没有找到 MCP 入口文件。"

    mcp_home = entry_file.parent
    vendor_path = mcp_home / "vendor"

    # 只导入服务器并读取名称，不调用任何 Abaqus 建模工具。
    python_code = (
        "import sys; "
        "sys.path.insert(0, {0!r}); "
        "import mcp_server; "
        "print('MCP_SERVER_NAME=' + mcp_server.mcp.name)"
    ).format(str(mcp_home))

    base_environment = os.environ.copy()
    # 禁止测试过程生成 Python 缓存文件。
    base_environment["PYTHONDONTWRITEBYTECODE"] = "1"

    attempts = []
    if vendor_path.is_dir():
        vendor_environment = base_environment.copy()
        old_python_path = vendor_environment.get("PYTHONPATH", "")
        # pip --target 不会自动执行 pywin32 的 .pth，因此显式加入其子目录。
        python_paths = [str(path) for path in vendor_python_paths(vendor_path)]
        if old_python_path:
            python_paths.append(old_python_path)
        vendor_environment["PYTHONPATH"] = os.pathsep.join(python_paths)
        attempts.append(("随附依赖", vendor_environment))

    # 某些 Windows 沙箱无法读取工作区外的 vendor 文件，因此增加系统依赖回退。
    system_environment = base_environment.copy()
    system_environment.pop("PYTHONPATH", None)
    attempts.append(("系统依赖", system_environment))

    last_error = "未知错误"
    for dependency_mode, environment in attempts:
        try:
            completed = subprocess.run(
                [sys.executable, "-c", python_code],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=environment,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_error = "使用{0}时导入测试超时。".format(dependency_mode)
            continue
        except OSError as error:
            last_error = "使用{0}时无法启动 Python：{1}".format(
                dependency_mode, error
            )
            continue

        output = _decode_output(completed.stdout)
        if completed.returncode == 0:
            for line in output.splitlines():
                if line.startswith("MCP_SERVER_NAME="):
                    server_name = line.split("=", 1)[1].strip()
                    message = "MCP 入口可以加载（使用{0}）。".format(
                        dependency_mode
                    )
                    return True, server_name, message
            last_error = "MCP 已导入，但没有返回服务器名称。"
            continue

        # 只保留最后一行错误，避免把完整环境和配置写入报告。
        error_lines = [line.strip() for line in output.splitlines() if line.strip()]
        last_error = error_lines[-1] if error_lines else "未知错误"

    return False, None, "MCP 导入失败：{0}".format(last_error)


def inspect_abaqus_mcp() -> Dict[str, object]:
    """汇总 Abaqus MCP 的三个独立状态。"""

    codex_cli, list_output = query_codex_mcp_list()
    registered_names = parse_abaqus_mcp_names(list_output) if codex_cli else []
    entry_file = default_mcp_entry()
    guard_file = default_mcp_guard()
    status_file = entry_file.parent / "status.json"
    files_installed = entry_file.is_file()

    if files_installed:
        launchable, server_name, launch_message = verify_local_mcp_import(entry_file)
    else:
        launchable = False
        server_name = None
        launch_message = "没有找到本地 Abaqus MCP 文件。"

    registered = bool(registered_names)
    usable = registered and launchable
    bridge = inspect_bridge_status(status_file)
    responsive = bool(bridge["responsive"])

    if usable and responsive:
        message = "Abaqus MCP 已注册，服务器和 Abaqus 插件均响应正常。"
    elif usable:
        message = "Abaqus MCP 已配置，但 Abaqus/CAE 插件当前没有响应。"
    elif files_installed and not registered:
        message = "Abaqus MCP 文件存在，但尚未注册到 Codex。"
    elif registered and not launchable:
        message = "Abaqus MCP 已注册，但本地启动验证失败。"
    else:
        message = "没有检测到可用的 Abaqus MCP。"

    return {
        "usable": usable,
        "codex_cli": str(codex_cli) if codex_cli else None,
        "files_installed": files_installed,
        "entry_file": str(entry_file),
        "guard_file": str(guard_file),
        "guard_installed": guard_file.is_file(),
        "registered": registered,
        "registered_names": registered_names,
        "launchable": launchable,
        "server_name": server_name,
        "launch_message": launch_message,
        "responsive": responsive,
        "bridge_status": bridge,
        "message": message,
    }


def main() -> int:
    """用适合初学者阅读的方式显示 MCP 检测结果。"""

    result = inspect_abaqus_mcp()

    print("Abaqus MCP 环境检测")
    print("---------------------")
    print("检测结果：{0}".format(result["message"]))
    print("服务器文件：{0}".format("存在" if result["files_installed"] else "不存在"))
    print("Codex 注册：{0}".format("已注册" if result["registered"] else "未注册"))
    print("启动验证：{0}".format("通过" if result["launchable"] else "未通过"))
    print("启动说明：{0}".format(result["launch_message"]))
    print("防卡启动器：{0}".format("已安装" if result["guard_installed"] else "未安装"))
    print("Abaqus 桥接：{0}".format("在线" if result["responsive"] else "离线"))
    print("桥接说明：{0}".format(result["bridge_status"]["message"]))

    if result["codex_cli"]:
        print("Codex CLI：{0}".format(result["codex_cli"]))
    if result["registered_names"]:
        print("注册名称：{0}".format(", ".join(result["registered_names"])))
    if result["server_name"]:
        print("服务器名称：{0}".format(result["server_name"]))

    return 0 if result["usable"] else 1


if __name__ == "__main__":
    sys.exit(main())
