# -*- coding: utf-8 -*-
"""通过官方 Codex App Server 提供只读中文咨询。"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from abaqus_codex import __version__
from abaqus_codex.desktop_assistant.codex_status import _find_codex_executable
from abaqus_codex.paths import user_data_root


MAX_PROTOCOL_LINE = 2 * 1024 * 1024
MAX_PROMPT_LENGTH = 4000
MAX_REPLY_LENGTH = 50000
DEFAULT_TIMEOUT_SECONDS = 180.0
SESSION_STATE_FILENAME = "codex_session.json"
THREAD_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{5,200}$")
ALLOWED_REASONING_EFFORTS = {"low", "medium", "high"}
RECTANGLE_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["ready", "needs_clarification", "unsupported"],
        },
        "model_name": {"type": "string"},
        "part_name": {"type": "string"},
        "length_mm": {"type": "number"},
        "width_mm": {"type": "number"},
        "message": {"type": "string"},
        "assumptions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "risks": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "status", "model_name", "part_name", "length_mm", "width_mm",
        "message", "assumptions", "risks",
    ],
    "additionalProperties": False,
}
BASE_INSTRUCTIONS = (
    "你是面向 Abaqus 2021 初学者的中文仿真咨询助手。"
    "本会话当前只能咨询，不能修改 Abaqus、不能运行命令、不能读取文件、"
    "不能调用 MCP 或其他工具。请用中文回答。"
    "当用户需求不完整时，先逐项追问几何、材料、单位、载荷、边界条件、"
    "接触、分析类型和验收指标。明确区分工程建议与已经执行的操作，"
    "不得声称模型已经创建或修改。"
)


class CodexAppServerError(RuntimeError):
    """App Server 无法启动、协议异常或咨询失败。"""


class CodexTurnInterrupted(CodexAppServerError):
    """用户主动停止了当前 Codex 回答。"""


@dataclass(frozen=True)
class CodexAccountInfo:
    """App Server 实时返回的脱敏账号信息。"""

    account_type: str
    masked_identifier: str
    plan_type: str

    @property
    def display_text(self) -> str:
        """返回适合界面显示的账号、套餐和实时连接说明。"""

        plan_labels = {
            "plus": "Plus",
            "pro": "Pro",
            "free": "Free",
            "team": "Team",
            "business": "Business",
            "enterprise": "Enterprise",
            "edu": "Edu",
            "edu_plus": "Edu Plus",
            "edu_pro": "Edu Pro",
        }
        plan = plan_labels.get(self.plan_type, self.plan_type or "未知套餐")
        return "App Server 已连接 · {0} · {1}".format(
            plan,
            self.masked_identifier,
        )


def mask_account_email(value: object) -> str:
    """保留足够辨认的信息，同时避免完整邮箱长期显示在屏幕上。"""

    email = str(value or "").strip()
    if "@" not in email:
        return "ChatGPT 账号"
    local, domain = email.split("@", 1)
    if not local or not domain:
        return "ChatGPT 账号"
    prefix = local[:1]
    return "{0}***@{1}".format(prefix, domain)


def normalize_ai_prompt(value: object) -> str:
    """清理控制字符并限制长度，保留正常中文换行。"""

    text = str(value).replace("\x00", "").strip()
    text = "".join(
        character
        for character in text
        if character in "\n\t" or ord(character) >= 32
    )
    return text[:MAX_PROMPT_LENGTH]


def default_ai_workspace() -> Path:
    """使用不含 CAE 文件的独立目录作为只读咨询工作区。"""

    return (user_data_root() / "ai_workspace").resolve()


class CodexReadOnlyClient:
    """维护一个会话期内复用的只读 Codex 线程。"""

    def __init__(
        self,
        *,
        executable: Optional[str] = None,
        workspace: Optional[Path] = None,
        process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.executable = executable
        self.workspace = (workspace or default_ai_workspace()).resolve()
        self.process_factory = process_factory
        self.timeout_seconds = timeout_seconds
        self.process: Optional[subprocess.Popen] = None
        self.thread_id: Optional[str] = None
        self.session_resumed = False
        self.account_info: Optional[CodexAccountInfo] = None
        self.active_turn_id: Optional[str] = None
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._active_turn_condition = threading.Condition()
        self._write_lock = threading.Lock()
        self._response_condition = threading.Condition()
        self._responses: dict[int, dict[str, object]] = {}
        self._notifications: queue.Queue[dict[str, object]] = queue.Queue()

    def start(self) -> None:
        """启动 stdio App Server，并创建禁止写入的临时咨询线程。"""

        if self.process is not None and self.thread_id:
            return
        executable = self.executable or _find_codex_executable()
        if not executable:
            raise CodexAppServerError("未找到 Codex，无法启动 AI 咨询。")
        self.workspace.mkdir(parents=True, exist_ok=True)
        creation_flags = 0
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.process = self.process_factory(
                [executable, "app-server", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=str(self.workspace),
                shell=False,
                creationflags=creation_flags,
            )
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            raise CodexAppServerError("无法启动 Codex App Server。") from error
        if self.process.stdin is None or self.process.stdout is None:
            self.close()
            raise CodexAppServerError("Codex App Server 没有建立通信管道。")

        reader = threading.Thread(target=self._reader_worker, daemon=True)
        reader.start()
        self._request(
            "initialize",
            {
                "clientInfo": {
                    "name": "abaqus_codex_assistant",
                    "title": "Abaqus 中文建模助手",
                    "version": __version__,
                }
            },
            timeout_seconds=15.0,
        )
        self._send({"method": "initialized", "params": {}})
        account_response = self._request(
            "account/read",
            {"refreshToken": False},
            timeout_seconds=20.0,
        )
        self.account_info = self._parse_account_info(account_response)
        common_thread_params: dict[str, object] = {
            "approvalPolicy": "never",
            "baseInstructions": BASE_INSTRUCTIONS,
            "cwd": str(self.workspace),
            "sandbox": "read-only",
        }
        saved_thread_id = self._load_saved_thread_id()
        response: Optional[dict[str, object]] = None
        if saved_thread_id:
            try:
                response = self._request(
                    "thread/resume",
                    dict(common_thread_params, threadId=saved_thread_id),
                    timeout_seconds=20.0,
                )
                self.session_resumed = True
            except CodexAppServerError:
                # 会话可能已被用户删除或属于旧版本；安全退回新建会话。
                response = None
                self.session_resumed = False
        if response is None:
            response = self._request(
                "thread/start",
                dict(common_thread_params, ephemeral=False),
                timeout_seconds=20.0,
            )
        result = response.get("result")
        thread = result.get("thread") if isinstance(result, dict) else None
        thread_id = thread.get("id") if isinstance(thread, dict) else None
        if not isinstance(thread_id, str) or not thread_id:
            self.close()
            raise CodexAppServerError("Codex 没有返回有效会话编号。")
        self.thread_id = thread_id
        self._save_thread_id(thread_id)

    @property
    def session_state_path(self) -> Path:
        """返回仅保存非凭据会话编号的本地状态文件。"""

        return self.workspace / SESSION_STATE_FILENAME

    def _load_saved_thread_id(self) -> Optional[str]:
        """读取上次会话编号；损坏或异常文件会被忽略。"""

        path = self.session_state_path
        try:
            if not path.is_file() or path.stat().st_size > 4096:
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError):
            return None
        thread_id = payload.get("thread_id") if isinstance(payload, dict) else None
        if not isinstance(thread_id, str) or THREAD_ID_PATTERN.fullmatch(thread_id) is None:
            return None
        return thread_id

    def _save_thread_id(self, thread_id: str) -> None:
        """只保存 threadId；不保存账号令牌、密码、提示词或回答正文。"""

        if THREAD_ID_PATTERN.fullmatch(thread_id) is None:
            raise CodexAppServerError("Codex 返回的会话编号格式无效。")
        payload = {"version": 1, "thread_id": thread_id}
        try:
            self.session_state_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        except OSError as error:
            raise CodexAppServerError("无法保存专属 Codex 会话编号。") from error

    @staticmethod
    def _parse_account_info(
        response: dict[str, object]
    ) -> CodexAccountInfo:
        """只接受官方账号字段，不读取本地认证缓存。"""

        result = response.get("result")
        account = result.get("account") if isinstance(result, dict) else None
        if not isinstance(account, dict):
            raise CodexAppServerError("App Server 没有返回已登录账号。")
        account_type = account.get("type")
        if account_type == "chatgpt":
            return CodexAccountInfo(
                account_type="chatgpt",
                masked_identifier=mask_account_email(account.get("email")),
                plan_type=str(account.get("planType") or "unknown"),
            )
        if account_type == "apiKey":
            return CodexAccountInfo(
                account_type="api_key",
                masked_identifier="API Key 账号",
                plan_type="按 API 用量计费",
            )
        raise CodexAppServerError("当前 Codex 账号类型不受本应用支持。")

    def ask(
        self,
        prompt: str,
        *,
        on_delta: Optional[Callable[[str], None]] = None,
        effort: Optional[str] = None,
    ) -> str:
        """发送一次中文咨询并返回最终回答；本方法应在后台线程调用。"""

        return self._run_turn(prompt, on_delta=on_delta, effort=effort)

    def extract_rectangle(
        self, prompt: str, *, effort: Optional[str] = None
    ) -> dict[str, object]:
        """让 Codex 只提取矩形参数；返回值仍需经过本地白名单校验。"""

        extraction_prompt = (
            "请判断下面的中文需求是否是在创建二维矩形板，并只提取明确给出的参数。"
            "不要猜测缺失尺寸，不要生成 Python、命令或 Abaqus action。"
            "如果长度、宽度、模型名或零件名缺失，status 设为 needs_clarification，"
            "并在 message 中用中文说明还需要什么；无关需求设为 unsupported。"
            "只有四项都明确且单位可换算为 mm 时，status 才能为 ready。\n\n"
            "用户输入：" + normalize_ai_prompt(prompt)
        )
        answer = self._run_turn(
            extraction_prompt,
            output_schema=RECTANGLE_EXTRACTION_SCHEMA,
            effort=effort,
        )
        try:
            payload = json.loads(answer)
        except (TypeError, ValueError) as error:
            raise CodexAppServerError("Codex 返回的矩形参数不是有效 JSON。") from error
        if not isinstance(payload, dict):
            raise CodexAppServerError("Codex 返回的矩形参数格式无效。")
        required = set(RECTANGLE_EXTRACTION_SCHEMA["required"])
        if set(payload) != required:
            raise CodexAppServerError("Codex 返回的矩形参数字段不完整。")
        if payload.get("status") not in {
            "ready", "needs_clarification", "unsupported"
        }:
            raise CodexAppServerError("Codex 返回了未知的识别状态。")
        return payload

    def _run_turn(
        self,
        prompt: str,
        *,
        on_delta: Optional[Callable[[str], None]] = None,
        output_schema: Optional[dict[str, object]] = None,
        effort: Optional[str] = None,
    ) -> str:
        """执行一轮只读生成；可选 schema 只约束当前这一轮。"""

        normalized = normalize_ai_prompt(prompt)
        if not normalized:
            raise CodexAppServerError("请输入需要咨询的问题。")
        self.start()
        if not self.thread_id:
            raise CodexAppServerError("Codex 咨询线程尚未建立。")

        turn_params: dict[str, object] = {
            "approvalPolicy": "never",
            "input": [{"type": "text", "text": normalized}],
            "sandboxPolicy": {
                "type": "readOnly",
                "networkAccess": False,
            },
            "threadId": self.thread_id,
        }
        if output_schema is not None:
            turn_params["outputSchema"] = output_schema
        if effort is not None:
            normalized_effort = str(effort).strip().lower()
            if normalized_effort not in ALLOWED_REASONING_EFFORTS:
                raise CodexAppServerError("不支持的 Codex 推理强度。")
            turn_params["effort"] = normalized_effort
        request_id = self._send_request("turn/start", turn_params)
        turn_response = self._wait_for_response(
            request_id,
            timeout_seconds=20.0,
        )
        result = turn_response.get("result")
        turn = result.get("turn") if isinstance(result, dict) else None
        turn_id = turn.get("id") if isinstance(turn, dict) else None
        if not isinstance(turn_id, str) or not turn_id:
            raise CodexAppServerError("Codex 没有返回有效回答编号。")
        with self._active_turn_condition:
            self.active_turn_id = turn_id
            self._active_turn_condition.notify_all()
        deadline = time.monotonic() + self.timeout_seconds
        streamed_parts: list[str] = []
        final_text = ""
        try:
            while time.monotonic() < deadline:
                remaining = max(0.05, deadline - time.monotonic())
                try:
                    message = self._notifications.get(timeout=min(0.5, remaining))
                except queue.Empty:
                    continue
                method = message.get("method")
                params = message.get("params")
                if not isinstance(params, dict):
                    params = {}
                if method == "item/agentMessage/delta":
                    delta = params.get("delta")
                    if isinstance(delta, str) and delta:
                        streamed_parts.append(delta)
                        if sum(len(part) for part in streamed_parts) > MAX_REPLY_LENGTH:
                            raise CodexAppServerError("Codex 回复超过本应用的安全长度限制。")
                        if on_delta is not None:
                            on_delta(delta)
                elif method == "item/completed":
                    item = params.get("item")
                    if isinstance(item, dict) and item.get("type") == "agentMessage":
                        text = item.get("text")
                        phase = item.get("phase")
                        if isinstance(text, str) and phase in (None, "final_answer"):
                            final_text = text
                elif method == "turn/completed":
                    completed_turn = params.get("turn")
                    status = (
                        completed_turn.get("status")
                        if isinstance(completed_turn, dict)
                        else None
                    )
                    if status == "interrupted":
                        raise CodexTurnInterrupted("用户已停止当前 Codex 回答。")
                    if status != "completed":
                        raise CodexAppServerError("Codex 本轮咨询没有正常完成。")
                    answer = final_text or "".join(streamed_parts)
                    if not answer.strip():
                        raise CodexAppServerError("Codex 没有返回可显示的文字答复。")
                    return answer[:MAX_REPLY_LENGTH]
                elif "id" in message and isinstance(method, str):
                    # 第一版不接受任何命令、文件或权限审批请求。
                    self._send(
                        {
                            "id": message["id"],
                            "error": {
                                "code": -32000,
                                "message": "read-only consultation rejects tool requests",
                            },
                        }
                    )
                elif method == "app-server/eof":
                    raise CodexAppServerError("Codex App Server 意外结束。")
            raise CodexAppServerError("等待 Codex 回复超时，请稍后重试。")
        finally:
            with self._active_turn_condition:
                if self.active_turn_id == turn_id:
                    self.active_turn_id = None
                self._active_turn_condition.notify_all()

    def interrupt(self, *, timeout_seconds: float = 10.0) -> None:
        """调用官方 turn/interrupt，只停止当前回答。"""

        deadline = time.monotonic() + min(timeout_seconds, 5.0)
        with self._active_turn_condition:
            while self.active_turn_id is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CodexAppServerError("当前没有可停止的 Codex 回答。")
                self._active_turn_condition.wait(timeout=remaining)
            turn_id = self.active_turn_id
        if not self.thread_id or not turn_id:
            raise CodexAppServerError("当前没有可停止的 Codex 回答。")
        self._request(
            "turn/interrupt",
            {"threadId": self.thread_id, "turnId": turn_id},
            timeout_seconds=timeout_seconds,
        )

    def _reader_worker(self) -> None:
        """持续读取 JSONL；原始协议内容不会进入应用日志。"""

        process = self.process
        if process is None or process.stdout is None:
            return
        try:
            for raw_line in process.stdout:
                if len(raw_line.encode("utf-8", errors="replace")) > MAX_PROTOCOL_LINE:
                    self._notifications.put({"method": "app-server/eof"})
                    return
                try:
                    message = json.loads(raw_line)
                except (TypeError, ValueError):
                    continue
                if not isinstance(message, dict):
                    continue
                message_id = message.get("id")
                if isinstance(message_id, int) and "method" not in message:
                    with self._response_condition:
                        self._responses[message_id] = message
                        self._response_condition.notify_all()
                else:
                    self._notifications.put(message)
        finally:
            self._notifications.put({"method": "app-server/eof"})

    def _send(self, message: dict[str, object]) -> None:
        """序列化单条 JSONL 消息，不经过 shell。"""

        process = self.process
        if process is None or process.stdin is None:
            raise CodexAppServerError("Codex App Server 尚未连接。")
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        try:
            with self._write_lock:
                process.stdin.write(payload + "\n")
                process.stdin.flush()
        except (OSError, ValueError) as error:
            raise CodexAppServerError("无法向 Codex 发送消息。") from error

    def _send_request(self, method: str, params: dict[str, object]) -> int:
        """发送请求并返回本地递增编号。"""

        with self._id_lock:
            request_id = self._next_id
            self._next_id += 1
        self._send({"id": request_id, "method": method, "params": params})
        return request_id

    def _wait_for_response(
        self, request_id: int, *, timeout_seconds: float
    ) -> dict[str, object]:
        """等待指定响应；通知由另一条队列保留给咨询循环。"""

        deadline = time.monotonic() + timeout_seconds
        with self._response_condition:
            while request_id not in self._responses:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CodexAppServerError("Codex App Server 响应超时。")
                self._response_condition.wait(timeout=remaining)
            response = self._responses.pop(request_id)
        error = response.get("error")
        if error is not None:
            raise CodexAppServerError("Codex App Server 拒绝了本次请求。")
        return response

    def _request(
        self,
        method: str,
        params: dict[str, object],
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        """发送并等待一个普通请求。"""

        request_id = self._send_request(method, params)
        return self._wait_for_response(
            request_id,
            timeout_seconds=timeout_seconds,
        )

    def close(self) -> None:
        """关闭本应用启动的子进程，不影响其他 Codex 窗口。"""

        process = self.process
        self.process = None
        self.thread_id = None
        self.account_info = None
        self.session_resumed = False
        with self._active_turn_condition:
            self.active_turn_id = None
            self._active_turn_condition.notify_all()
        if process is None:
            return
        try:
            process.terminate()
        except (OSError, AttributeError):
            pass


__all__ = [
    "CodexAppServerError",
    "CodexAccountInfo",
    "CodexReadOnlyClient",
    "CodexTurnInterrupted",
    "ALLOWED_REASONING_EFFORTS",
    "RECTANGLE_EXTRACTION_SCHEMA",
    "SESSION_STATE_FILENAME",
    "mask_account_email",
    "normalize_ai_prompt",
]
