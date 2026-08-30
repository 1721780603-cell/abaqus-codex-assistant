# -*- coding: utf-8 -*-
"""用内存假进程验证只读 Codex App Server 客户端。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from abaqus_codex.desktop_assistant.codex_app_server import (
    CodexReadOnlyClient,
    MAX_PROMPT_LENGTH,
    RECTANGLE_EXTRACTION_SCHEMA,
    mask_account_email,
    normalize_ai_prompt,
)


class FakeInput:
    """记录客户端发送的 JSONL，不访问真实进程。"""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def write(self, value: str) -> int:
        self.lines.append(value)
        return len(value)

    def flush(self) -> None:
        pass


class FakeProcess:
    """按固定顺序返回握手、流式回复和完成事件。"""

    def __init__(self, messages: list[dict[str, object]]) -> None:
        self.stdin = FakeInput()
        self.stdout = iter(
            [json.dumps(message, ensure_ascii=False) + "\n" for message in messages]
        )
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True


def successful_messages() -> list[dict[str, object]]:
    """返回一次完整咨询所需的最小协议消息。"""

    return [
        {"id": 1, "result": {}},
        {
            "id": 2,
            "result": {
                "account": {
                    "email": "student@example.com",
                    "planType": "plus",
                    "type": "chatgpt",
                },
                "requiresOpenaiAuth": True,
            },
        },
        {"id": 3, "result": {"thread": {"id": "thr_test"}}},
        {"id": 4, "result": {"turn": {"id": "turn_test"}}},
        {
            "method": "item/agentMessage/delta",
            "params": {
                "delta": "需要先确认坡高和土体参数。",
                "itemId": "item_test",
                "threadId": "thr_test",
                "turnId": "turn_test",
            },
        },
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "id": "item_test",
                    "phase": "final_answer",
                    "text": "请提供坡高、坡角、土层参数和地下水位。",
                    "type": "agentMessage",
                },
                "threadId": "thr_test",
                "turnId": "turn_test",
            },
        },
        {
            "method": "turn/completed",
            "params": {
                "threadId": "thr_test",
                "turn": {
                    "id": "turn_test",
                    "items": [],
                    "status": "completed",
                },
            },
        },
    ]


class CodexAppServerTests(unittest.TestCase):
    """确认咨询通道无法获得 Abaqus 或文件写权限。"""

    def test_read_only_conversation_returns_final_answer(self):
        """握手和一轮问答使用只读、禁网、永不审批设置。"""

        fake_process = FakeProcess(successful_messages())
        process_arguments = {}

        def process_factory(command, **kwargs):
            process_arguments["command"] = command
            process_arguments["kwargs"] = kwargs
            return fake_process

        with tempfile.TemporaryDirectory() as directory:
            client = CodexReadOnlyClient(
                executable=r"C:\safe\codex.exe",
                workspace=Path(directory),
                process_factory=process_factory,
                timeout_seconds=1.0,
            )
            deltas = []
            answer = client.ask(
                "我想分析边坡稳定",
                on_delta=deltas.append,
                effort="low",
            )
            account_display = client.account_info.display_text
            client.close()

        sent = [
            json.loads(line)
            for line in fake_process.stdin.lines
            if line.strip()
        ]
        thread_request = next(
            message for message in sent if message.get("method") == "thread/start"
        )
        turn_request = next(
            message for message in sent if message.get("method") == "turn/start"
        )
        self.assertEqual(thread_request["params"]["sandbox"], "read-only")
        self.assertEqual(thread_request["params"]["approvalPolicy"], "never")
        self.assertFalse(thread_request["params"]["ephemeral"])
        self.assertEqual(
            turn_request["params"]["sandboxPolicy"],
            {"type": "readOnly", "networkAccess": False},
        )
        self.assertEqual(turn_request["params"]["approvalPolicy"], "never")
        self.assertEqual(turn_request["params"]["effort"], "low")
        self.assertEqual(
            turn_request["params"]["input"][0]["text"],
            "我想分析边坡稳定",
        )
        self.assertEqual(answer, "请提供坡高、坡角、土层参数和地下水位。")
        self.assertEqual(deltas, ["需要先确认坡高和土体参数。"])
        self.assertEqual(
            account_display,
            "App Server 已连接 · Plus · s***@example.com",
        )
        account_request = next(
            message for message in sent if message.get("method") == "account/read"
        )
        self.assertFalse(account_request["params"]["refreshToken"])
        self.assertEqual(client.account_info, None)
        self.assertFalse(process_arguments["kwargs"]["shell"])
        self.assertTrue(fake_process.terminated)

    def test_saved_thread_is_resumed_without_storing_credentials(self):
        """第二次启动恢复专属会话，状态文件不得包含账号或回答正文。"""

        messages = successful_messages()
        messages[2]["result"]["thread"]["id"] = "thr_saved"
        fake_process = FakeProcess(messages[:3])

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            state_path = workspace / "codex_session.json"
            state_path.write_text(
                json.dumps({"version": 1, "thread_id": "thr_saved"}),
                encoding="utf-8",
            )
            client = CodexReadOnlyClient(
                executable=r"C:\safe\codex.exe",
                workspace=workspace,
                process_factory=lambda *_args, **_kwargs: fake_process,
                timeout_seconds=1.0,
            )
            client.start()
            self.assertTrue(client.session_resumed)
            saved_text = state_path.read_text(encoding="utf-8")
            client.close()

        sent = [json.loads(line) for line in fake_process.stdin.lines if line.strip()]
        resume_request = next(
            message for message in sent if message.get("method") == "thread/resume"
        )
        self.assertEqual(resume_request["params"]["threadId"], "thr_saved")
        self.assertFalse(
            any(message.get("method") == "thread/start" for message in sent)
        )
        self.assertIn("thr_saved", saved_text)
        self.assertNotIn("student@example.com", saved_text)
        self.assertNotIn("需要先确认", saved_text)

    def test_account_email_is_masked_for_display(self):
        """界面只显示足够辨认的邮箱，不完整展示账号。"""

        self.assertEqual(
            mask_account_email("student@example.com"),
            "s***@example.com",
        )

    def test_interrupt_uses_current_thread_and_turn(self):
        """停止按钮只能调用官方 turn/interrupt。"""

        messages = successful_messages()[:3] + [{"id": 4, "result": {}}]
        fake_process = FakeProcess(messages)

        with tempfile.TemporaryDirectory() as directory:
            client = CodexReadOnlyClient(
                executable=r"C:\safe\codex.exe",
                workspace=Path(directory),
                process_factory=lambda *_args, **_kwargs: fake_process,
                timeout_seconds=1.0,
            )
            client.start()
            with client._active_turn_condition:
                client.active_turn_id = "turn_active"
                client._active_turn_condition.notify_all()
            client.interrupt(timeout_seconds=1.0)
            client.close()

        sent = [json.loads(line) for line in fake_process.stdin.lines if line.strip()]
        interrupt_request = next(
            message
            for message in sent
            if message.get("method") == "turn/interrupt"
        )
        self.assertEqual(
            interrupt_request["params"],
            {"threadId": "thr_test", "turnId": "turn_active"},
        )

    def test_prompt_is_bounded_and_control_characters_removed(self):
        """用户输入不能无限增长或携带空字符。"""

        prompt = normalize_ai_prompt("边坡\x00\n" + "x" * 5000)
        self.assertNotIn("\x00", prompt)
        self.assertIn("\n", prompt)
        self.assertLessEqual(len(prompt), MAX_PROMPT_LENGTH)

    def test_rectangle_extraction_uses_current_turn_output_schema(self):
        """AI 只返回固定字段，且 App Server 仍保持只读和禁网。"""

        messages = successful_messages()
        structured = {
            "status": "ready",
            "model_name": "Model-1",
            "part_name": "Plate",
            "length_mm": 100.0,
            "width_mm": 20.0,
            "message": "参数完整。",
            "assumptions": [],
            "risks": ["只创建几何。"],
        }
        structured_text = json.dumps(structured, ensure_ascii=False)
        messages[4]["params"]["delta"] = structured_text
        messages[5]["params"]["item"]["text"] = structured_text
        fake_process = FakeProcess(messages)

        with tempfile.TemporaryDirectory() as directory:
            client = CodexReadOnlyClient(
                executable=r"C:\safe\codex.exe",
                workspace=Path(directory),
                process_factory=lambda *_args, **_kwargs: fake_process,
                timeout_seconds=1.0,
            )
            result = client.extract_rectangle(
                "做一个长100毫米、宽20毫米的板，模型Model-1，零件Plate"
            )
            client.close()

        sent = [json.loads(line) for line in fake_process.stdin.lines if line.strip()]
        turn_request = next(
            message for message in sent if message.get("method") == "turn/start"
        )
        self.assertEqual(
            turn_request["params"]["outputSchema"],
            RECTANGLE_EXTRACTION_SCHEMA,
        )
        self.assertEqual(
            turn_request["params"]["sandboxPolicy"],
            {"type": "readOnly", "networkAccess": False},
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["length_mm"], 100.0)


if __name__ == "__main__":
    unittest.main()
