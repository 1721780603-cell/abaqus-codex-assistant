# -*- coding: utf-8 -*-
"""检测本机是否安装 Abaqus，并读取 Abaqus 版本。"""

from __future__ import annotations

import locale
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple


# 同时兼容 Abaqus 2021 一类的新版本号，以及 Abaqus 6.14-5 一类的旧版本号。
ABAQUS_VERSION_PATTERN = re.compile(
    r"\bAbaqus\s+((?:20\d{2})|(?:6\.\d+(?:-\d+)?))\b",
    re.IGNORECASE,
)

# 查询脚本使用固定标记，避免把 Abaqus 启动时输出的其他版本号误认为 Python 版本。
ABAQUS_PYTHON_VERSION_PATTERN = re.compile(
    r"^ABAQUS_PYTHON_VERSION=(.+)$", re.MULTILINE
)
ABAQUS_PYTHON_EXECUTABLE_PATTERN = re.compile(
    r"^ABAQUS_PYTHON_EXECUTABLE=(.+)$", re.MULTILINE
)


def parse_abaqus_version(output: str) -> Optional[str]:
    """从 Abaqus 的版本查询输出中提取版本号。"""

    match = ABAQUS_VERSION_PATTERN.search(output)
    if match is None:
        return None
    return match.group(1)


def parse_abaqus_python_info(output: str) -> Tuple[Optional[str], Optional[str]]:
    """从带标记的输出中提取 Abaqus Python 版本和路径。"""

    version_match = ABAQUS_PYTHON_VERSION_PATTERN.search(output)
    executable_match = ABAQUS_PYTHON_EXECUTABLE_PATTERN.search(output)

    version = version_match.group(1).strip() if version_match else None
    executable = executable_match.group(1).strip() if executable_match else None
    return version, executable


def _command_names() -> list[str]:
    """生成需要依次查找的 Abaqus 命令名称。"""

    # 优先使用通用命令；找不到时再尝试 abq2021 这样的版本命令。
    names = ["abaqus"]
    newest_year = datetime.now().year + 1
    names.extend("abq{0}".format(year) for year in range(newest_year, 2015, -1))
    return names


def _common_windows_paths() -> list[Path]:
    """返回 Windows 上常见的 Abaqus 命令路径。"""

    paths = [Path(r"C:\SIMULIA\Commands\abaqus.bat")]

    # 某些安装方式会使用 C:\ABAQUS2021\commands 这样的目录。
    system_root = Path("C:/")
    if system_root.exists():
        paths.extend(system_root.glob("ABAQUS*/commands/abaqus.bat"))
        paths.extend(system_root.glob("ABAQUS*/commands/abq*.bat"))

    return paths


def find_abaqus_command() -> Optional[Path]:
    """从系统命令和常见目录中寻找 Abaqus 启动命令。"""

    for name in _command_names():
        command = shutil.which(name)
        if command:
            return Path(command).resolve()

    if os.name == "nt":
        for path in _common_windows_paths():
            if path.is_file():
                return path.resolve()

    return None


def _decode_output(data: bytes) -> str:
    """使用常见编码读取 Abaqus 的命令行输出。"""

    encodings = ["utf-8", locale.getpreferredencoding(False), "gbk"]
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue

    # 如果无法完整识别编码，保留可读取字符并替换异常字节。
    return data.decode("utf-8", errors="replace")


def query_abaqus_release(
    command: Path, timeout_seconds: int = 60
) -> Tuple[int, str]:
    """执行只读版本查询，并返回退出码和输出文本。"""

    if os.name == "nt" and command.suffix.lower() in {".bat", ".cmd"}:
        # Windows 的批处理文件需要交给 cmd.exe 执行。
        arguments = [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            str(command),
            "information=release",
        ]
    else:
        arguments = [str(command), "information=release"]

    completed = subprocess.run(
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout_seconds,
        check=False,
    )
    return completed.returncode, _decode_output(completed.stdout)


def query_abaqus_python(
    command: Path, timeout_seconds: int = 60
) -> Tuple[int, str]:
    """运行 Abaqus 自带 Python，并读取其版本和可执行文件路径。"""

    # 这段代码兼容 Abaqus 2021 使用的 Python 2.7。
    python_code = (
        "import sys; "
        "print('ABAQUS_PYTHON_VERSION=' + sys.version.split()[0]); "
        "print('ABAQUS_PYTHON_EXECUTABLE=' + sys.executable)"
    )

    if os.name == "nt" and command.suffix.lower() in {".bat", ".cmd"}:
        # Windows 的批处理命令需要由 cmd.exe 解释。
        arguments = [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            str(command),
            "python",
            "-c",
            python_code,
        ]
    else:
        arguments = [str(command), "python", "-c", python_code]

    completed = subprocess.run(
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout_seconds,
        check=False,
    )
    return completed.returncode, _decode_output(completed.stdout)


def inspect_abaqus_command(command: Path) -> Dict[str, object]:
    """检查一条明确的 Abaqus 命令，避免检测和实际启动指向不同版本。"""

    command = Path(command).resolve()

    try:
        return_code, output = query_abaqus_release(command)
    except subprocess.TimeoutExpired:
        return {
            "installed": True,
            "usable": False,
            "command": str(command),
            "version": None,
            "python_version": None,
            "python_executable": None,
            "message": "Abaqus 版本查询超时。",
        }
    except OSError as error:
        return {
            "installed": True,
            "usable": False,
            "command": str(command),
            "version": None,
            "python_version": None,
            "python_executable": None,
            "message": "无法启动 Abaqus：{0}".format(error),
        }

    version = parse_abaqus_version(output)
    release_usable = return_code == 0 and version is not None
    if not release_usable:
        if return_code != 0:
            message = "找到了 Abaqus 命令，但版本查询失败。"
        else:
            message = "Abaqus 命令可以运行，但没有识别出版本号。"

        return {
            "installed": True,
            "usable": False,
            "command": str(command),
            "version": version,
            "python_version": None,
            "python_executable": None,
            "message": message,
        }

    try:
        python_return_code, python_output = query_abaqus_python(command)
    except subprocess.TimeoutExpired:
        return {
            "installed": True,
            "usable": False,
            "command": str(command),
            "version": version,
            "python_version": None,
            "python_executable": None,
            "message": "Abaqus 可用，但自带 Python 查询超时。",
        }
    except OSError as error:
        return {
            "installed": True,
            "usable": False,
            "command": str(command),
            "version": version,
            "python_version": None,
            "python_executable": None,
            "message": "Abaqus 可用，但无法启动自带 Python：{0}".format(error),
        }

    python_version, python_executable = parse_abaqus_python_info(python_output)
    python_usable = (
        python_return_code == 0
        and python_version is not None
        and python_executable is not None
    )
    if python_usable:
        message = "已找到可用的 Abaqus 及其自带 Python。"
    else:
        message = "Abaqus 可用，但没有正确读取自带 Python 信息。"

    return {
        "installed": True,
        "usable": python_usable,
        "command": str(command),
        "version": version,
        "python_version": python_version,
        "python_executable": python_executable,
        "message": message,
    }


def inspect_abaqus() -> Dict[str, object]:
    """查找默认 Abaqus 命令，再使用同一套规则读取版本和内置 Python。"""

    command = find_abaqus_command()
    if command is None:
        return {
            "installed": False,
            "usable": False,
            "command": None,
            "version": None,
            "python_version": None,
            "python_executable": None,
            "message": "没有找到 Abaqus 启动命令。",
        }
    return inspect_abaqus_command(command)


def main() -> int:
    """以适合初学者阅读的格式显示检测结果。"""

    result = inspect_abaqus()

    print("Abaqus 环境检测")
    print("-----------------")
    print("检测结果：{0}".format(result["message"]))

    if result["command"]:
        print("启动命令：{0}".format(result["command"]))
    if result["version"]:
        print("Abaqus 版本：{0}".format(result["version"]))
    if result["python_version"]:
        print("自带 Python 版本：{0}".format(result["python_version"]))
    if result["python_executable"]:
        print("自带 Python 路径：{0}".format(result["python_executable"]))

    # 退出码 0 表示检测通过；退出码 1 表示需要用户处理环境问题。
    return 0 if result["usable"] else 1


if __name__ == "__main__":
    sys.exit(main())
