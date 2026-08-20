# -*- coding: utf-8 -*-
"""测试本地 AI 服务边界、结构化输出和配置白名单。"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from abaqus_codex.local_ai import (
    LocalAIError,
    build_rectangle_config,
    generate_rectangle_config,
    list_models,
    resolve_base_url,
    save_generated_config,
)


def valid_extraction():
    """返回一份符合本地 AI 白名单的参数提取结果。"""

    return {
        "length": 200.0,
        "height": 100.0,
        "thickness": 2.0,
        "material_name": None,
        "youngs_modulus": None,
        "poisson_ratio": None,
        "right_edge_displacement": 0.2,
        "mesh_size": None,
        "num_cpus": None,
        "errors": [],
    }


class LocalAIAddressTests(unittest.TestCase):
    """确认本地 AI 不能被改成任意外部网络请求器。"""

    def test_default_addresses_are_loopback(self):
        """两种服务默认地址都必须位于当前电脑。"""

        self.assertEqual(resolve_base_url("ollama"), "http://127.0.0.1:11434")
        self.assertEqual(resolve_base_url("lm-studio"), "http://127.0.0.1:1234")

    def test_external_address_is_rejected(self):
        """公网、局域网和带路径地址不能绕过本地数据边界。"""

        for value in (
            "https://example.com",
            "http://192.168.1.10:11434",
            "http://127.0.0.1:11434/proxy",
        ):
            with self.subTest(value=value), self.assertRaises(LocalAIError):
                resolve_base_url("ollama", value)


class LocalAIModelListTests(unittest.TestCase):
    """确认两种官方模型列表响应都能稳定解析。"""

    @patch("abaqus_codex.local_ai.request_json")
    def test_ollama_model_list(self, request_json_mock):
        """Ollama 使用 /api/tags 返回本机模型名称。"""

        request_json_mock.return_value = {
            "models": [{"name": "qwen2.5:7b"}, {"model": "gemma3:4b"}]
        }
        self.assertEqual(
            list_models("ollama"), ["gemma3:4b", "qwen2.5:7b"]
        )
        self.assertEqual(request_json_mock.call_args.args[0], "http://127.0.0.1:11434/api/tags")

    @patch("abaqus_codex.local_ai.request_json")
    def test_lm_studio_model_list_uses_optional_token(self, request_json_mock):
        """LM Studio 使用 /v1/models，并只从环境变量读取可选令牌。"""

        request_json_mock.return_value = {"data": [{"id": "local-model"}]}
        with patch.dict(os.environ, {"LM_API_TOKEN": "private-token"}):
            self.assertEqual(list_models("lm-studio"), ["local-model"])
        self.assertEqual(
            request_json_mock.call_args.args[0], "http://127.0.0.1:1234/v1/models"
        )
        self.assertEqual(request_json_mock.call_args.kwargs["token"], "private-token")


class LocalAIGenerationTests(unittest.TestCase):
    """确认 AI 只能生成矩形板白名单参数。"""

    @patch("abaqus_codex.local_ai.request_json")
    def test_ollama_generation_merges_verified_defaults(self, request_json_mock):
        """未明确给出的值应沿用教学默认值并清楚列出。"""

        request_json_mock.side_effect = [
            {"models": [{"name": "qwen2.5:7b"}]},
            {"message": {"content": json.dumps(valid_extraction())}},
        ]
        config, defaulted = generate_rectangle_config(
            "ollama",
            "qwen2.5:7b",
            "建立 200 x 100 x 2 mm 的矩形板，右边拉伸 0.2 mm。",
        )
        self.assertEqual(config["model"]["length"], 200.0)
        self.assertEqual(config["analysis"]["right_edge_displacement"], 0.2)
        self.assertEqual(config["material"]["youngs_modulus"], 210000.0)
        self.assertIn("youngs_modulus", defaulted)
        payload = request_json_mock.call_args_list[1].args[1]
        self.assertEqual(payload["stream"], False)
        self.assertEqual(payload["options"]["temperature"], 0)
        self.assertIn("format", payload)

    @patch("abaqus_codex.local_ai.request_json")
    def test_lm_studio_generation_uses_json_schema(self, request_json_mock):
        """LM Studio 请求必须启用严格 JSON Schema，而不是解析自由文本。"""

        request_json_mock.side_effect = [
            {"data": [{"id": "local-model"}]},
            {
                "choices": [
                    {"message": {"content": json.dumps(valid_extraction())}}
                ]
            },
        ]
        config, _ = generate_rectangle_config(
            "lm-studio", "local-model", "生成矩形板拉伸模型。"
        )
        self.assertEqual(config["model"]["type"], "rectangle")
        payload = request_json_mock.call_args_list[1].args[1]
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertEqual(
            request_json_mock.call_args_list[1].args[0],
            "http://127.0.0.1:1234/v1/chat/completions",
        )

    @patch("abaqus_codex.local_ai.request_json")
    def test_missing_local_model_is_rejected_before_generation(self, request_json_mock):
        """指定模型不存在时不应继续发送生成请求。"""

        request_json_mock.return_value = {"models": []}
        with self.assertRaises(LocalAIError):
            generate_rectangle_config("ollama", "missing", "生成矩形板。")
        self.assertEqual(request_json_mock.call_count, 1)

    def test_model_reported_errors_stop_generation(self):
        """单位或模型类型不受支持时不能悄悄使用猜测值。"""

        extraction = valid_extraction()
        extraction["errors"] = ["第一版不支持英寸。"]
        with self.assertRaises(LocalAIError):
            build_rectangle_config(extraction)

    def test_partial_material_parameters_are_rejected(self):
        """材料名称和力学参数不能与默认钢材参数混搭。"""

        extraction = valid_extraction()
        extraction["material_name"] = "Aluminum"
        with self.assertRaisesRegex(LocalAIError, "必须一起明确给出"):
            build_rectangle_config(extraction)

    @patch("abaqus_codex.local_ai.request_json")
    def test_unsupported_units_are_rejected_before_network_request(
        self, request_json_mock
    ):
        """GPa 等单位必须先由用户换算，不能让模型暗中换算。"""

        with self.assertRaisesRegex(LocalAIError, "只接受 mm 和 MPa"):
            generate_rectangle_config(
                "ollama", "qwen2.5:7b", "弹性模量为 210 GPa。"
            )
        request_json_mock.assert_not_called()

    def test_unknown_ai_field_is_rejected(self):
        """即使模型输出额外脚本字段，也不能进入项目配置。"""

        extraction = valid_extraction()
        extraction["script_path"] = "dangerous.py"
        with self.assertRaises(LocalAIError):
            build_rectangle_config(extraction)

    def test_non_finite_number_is_rejected(self):
        """NaN 和 Infinity 不能成为 Abaqus 尺寸或材料参数。"""

        for value in (float("nan"), float("inf"), float("-inf")):
            extraction = valid_extraction()
            extraction["length"] = value
            with self.subTest(value=value), self.assertRaises(LocalAIError):
                build_rectangle_config(extraction)

    def test_saved_config_is_valid_json_but_does_not_run_abaqus(self):
        """保存步骤只写 JSON，供用户检查后再单独运行。"""

        config, _ = build_rectangle_config(valid_extraction())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rectangle.json"
            save_generated_config(path, config)
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["analysis"]["job_name"], "local_ai_rectangle_2d")
        self.assertNotIn("script", saved)


if __name__ == "__main__":
    unittest.main()
