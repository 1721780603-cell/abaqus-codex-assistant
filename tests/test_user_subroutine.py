# -*- coding: utf-8 -*-
"""测试移动轮载 Fortran 模板的安全生成。"""

import tempfile
import unittest
from pathlib import Path

from abaqus_codex.configuration import validate_config
from abaqus_codex.user_subroutine import prepare_user_subroutine
from test_configuration import valid_config, valid_moving_load_config


class UserSubroutineGenerationTests(unittest.TestCase):
    """确保只有内置移动轮载模型会生成受控 DLOAD 文件。"""

    def test_regular_model_does_not_generate_subroutine(self):
        """二维普通模型不应无故要求 Fortran 编译器。"""

        with tempfile.TemporaryDirectory() as directory:
            path = prepare_user_subroutine(
                validate_config(valid_config()), Path(directory)
            )
        self.assertIsNone(path)

    def test_moving_load_parameters_are_written(self):
        """压力、速度和起点应写入本次运行专用的 Fortran 文件。"""

        config = validate_config(valid_moving_load_config())
        with tempfile.TemporaryDirectory() as directory:
            path = prepare_user_subroutine(config, Path(directory))
            source = path.read_text(encoding="utf-8")

        self.assertNotIn("@", source)
        self.assertIn("PRESSURE=7.000000000000000D-01", source)
        self.assertIn("SPEED=1.000000000000000D+04", source)
        self.assertIn("XSTART=-1.000000000000000D+02", source)
        self.assertIn("SUBROUTINE DLOAD", source)
        self.assertIn("初学者三维路面示例", source)


if __name__ == "__main__":
    unittest.main()
