# -*- coding: utf-8 -*-
"""测试模型类型与内置 Abaqus 脚本之间的安全映射。"""

import unittest

from abaqus_codex.configuration import validate_config
from abaqus_codex.workflow import _abaqus_script_for_config
from test_configuration import valid_config, valid_hole_config


class AbaqusScriptSelectionTests(unittest.TestCase):
    """确保配置只能选择项目内明确支持的脚本。"""

    def test_rectangle_uses_original_script(self):
        """旧矩形板配置应继续选择原始脚本。"""

        config = validate_config(valid_config())
        self.assertEqual(
            _abaqus_script_for_config(config).name, "rectangle_tension.py"
        )

    def test_hole_plate_uses_new_script(self):
        """圆孔板配置应选择新的圆孔建模脚本。"""

        config = validate_config(valid_hole_config())
        self.assertEqual(
            _abaqus_script_for_config(config).name,
            "plate_with_hole_tension.py",
        )


if __name__ == "__main__":
    unittest.main()
