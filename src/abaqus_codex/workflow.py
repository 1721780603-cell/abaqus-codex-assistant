# -*- coding: utf-8 -*-
"""协调配置校验、abqpy 调用、结果读取和中文报告生成。"""

from __future__ import annotations

import json
import locale
import math
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from abaqus_codex.configuration import load_rectangle_config, write_json
from abaqus_codex.report import write_chinese_report


def find_abqpy_command() -> Optional[Path]:
    """优先寻找当前虚拟环境中的 abqpy，再检查系统 PATH。"""

    script_name = "abqpy.exe" if sys.platform == "win32" else "abqpy"
    local_command = Path(sys.executable).resolve().parent / script_name
    if local_command.is_file():
        return local_command

    path_command = shutil.which("abqpy")
    return Path(path_command).resolve() if path_command else None


def _decode_output(data: bytes) -> str:
    """兼容 UTF-8、Windows 本地编码和无法识别的 Abaqus 输出。"""

    for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk"):
        try:
            return data.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return data.decode("utf-8", errors="replace")


def _load_results(path: Path) -> Dict[str, object]:
    """读取并检查 Abaqus 产生的核心结果字段。"""

    try:
        with path.open("r", encoding="utf-8") as stream:
            results = json.load(stream)
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("无法读取 Abaqus 结果文件：{0}".format(error)) from error

    required = ("maximum_displacement", "maximum_mises_stress", "config")
    missing = [key for key in required if key not in results]
    if missing:
        raise RuntimeError("结果文件缺少字段：{0}".format(", ".join(missing)))

    for key in ("maximum_displacement", "maximum_mises_stress"):
        value = float(results[key])
        if not math.isfinite(value) or value < 0.0:
            raise RuntimeError("结果字段 {0} 不是有效非负数。".format(key))
    return results


def run_rectangle_analysis(
    config_path: Path,
    work_root: Path,
    output_root: Path,
    timeout_seconds: int = 1800,
) -> Dict[str, object]:
    """运行一次独立分析，并返回结果和报告的绝对路径。"""

    if timeout_seconds < 1:
        raise RuntimeError("运行超时秒数必须大于零。")

    config = load_rectangle_config(config_path)
    abqpy_command = find_abqpy_command()
    if abqpy_command is None:
        raise RuntimeError("没有找到 abqpy，请先运行环境体检并安装匹配版本。")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    work_dir = work_root / run_id
    output_dir = output_root / run_id
    work_dir.mkdir(parents=True, exist_ok=False)
    output_dir.mkdir(parents=True, exist_ok=False)

    normalized_config_path = work_dir / "input_config.json"
    published_config_path = output_dir / "input_config.json"
    results_path = output_dir / "results.json"
    report_path = output_dir / "report.md"
    console_log_path = work_dir / "abaqus_console.log"
    write_json(normalized_config_path, config)
    write_json(published_config_path, config)

    abaqus_script = (
        Path(__file__).resolve().parent
        / "abaqus_scripts"
        / "rectangle_tension.py"
    )
    command = [
        str(abqpy_command),
        "cae",
        str(abaqus_script),
        str(normalized_config_path),
        str(results_path),
    ]

    try:
        completed = subprocess.run(
            command,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        console_output = _decode_output(error.stdout or b"")
        console_log_path.write_text(console_output, encoding="utf-8")
        raise RuntimeError(
            "Abaqus 运行超过 {0} 秒，已停止等待。日志：{1}".format(
                timeout_seconds, console_log_path
            )
        ) from error
    except OSError as error:
        raise RuntimeError("无法启动 abqpy：{0}".format(error)) from error

    console_output = _decode_output(completed.stdout)
    console_log_path.write_text(console_output, encoding="utf-8", newline="\n")
    if completed.returncode != 0:
        tail = "\n".join(console_output.splitlines()[-20:])
        raise RuntimeError(
            "Abaqus 返回退出码 {0}。最后输出：\n{1}".format(
                completed.returncode, tail
            )
        )
    if not results_path.is_file():
        raise RuntimeError(
            "Abaqus 已结束，但没有生成结果 JSON。请检查日志：{0}".format(
                console_log_path
            )
        )

    results = _load_results(results_path)
    write_chinese_report(report_path, results)
    return {
        "run_id": run_id,
        "work_dir": str(work_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "results_path": str(results_path.resolve()),
        "report_path": str(report_path.resolve()),
        "console_log_path": str(console_log_path.resolve()),
        "maximum_displacement": results["maximum_displacement"],
        "maximum_mises_stress": results["maximum_mises_stress"],
    }
