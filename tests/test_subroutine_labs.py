"""Offline checks for the fixed teaching input decks."""
from pathlib import Path
import tempfile
import unittest

from abaqus_codex.subroutine_labs import INPUTS, LABS, LAB_TITLES, export_lab
from abaqus_codex.cli import main


class SubroutineLabTests(unittest.TestCase):
    def test_all_labs_have_chinese_instructions_and_matching_commands(self):
        """七个案例均提供中文说明，且命令只引用该案例的实际文件。"""
        self.assertEqual(set(LABS), set(LAB_TITLES))
        with tempfile.TemporaryDirectory() as tmp:
            for lab in LABS:
                with self.subTest(lab=lab):
                    folder = export_lab(lab, Path(tmp) / lab)
                    readme = (folder / "README.md").read_text("utf-8")
                    self.assertIn(LAB_TITLES[lab], readme)
                    self.assertIn("尚未完成真实 Abaqus/Fortran 验证", readme)
                    self.assertIn("<已核对的 Abaqus 启动命令绝对路径>", readme)
                    self.assertIn("user=" + INPUTS[lab][2], readme)
                    self.assertIn("input=reference.inp interactive", readme)
                    self.assertIn(INPUTS[lab][3], readme)
                    self.assertIn(INPUTS[lab][4], readme)
                    self.assertIn("verification.md", readme)
                    self.assertIn("不会自动读取本实验的 ODB", readme)
                    self.assertIn("理论接近零时应报告绝对误差", readme)

    def test_verification_record_starts_with_no_claimed_results(self):
        """记录保留失败和缺失项；导出不能冒充求解成功或自动验收。"""
        with tempfile.TemporaryDirectory() as tmp:
            for lab in LABS:
                with self.subTest(lab=lab):
                    folder = export_lab(lab, Path(tmp) / lab)
                    record = (folder / "verification.md").read_text("utf-8")
                    self.assertIn("案例标识：`" + lab + "`", record)
                    self.assertIn("未运行 / 未核对", record)
                    self.assertIn("Abaqus 年份及补丁", record)
                    self.assertIn("项目 Python 版本：待填写", record)
                    self.assertIn("Fortran 和 Visual Studio 版本", record)
                    self.assertIn("user 实测", record)
                    self.assertIn("reference 实测", record)
                    self.assertIn("误差及容限依据", record)
                    self.assertIn("物理验证（实验或独立证据）：未完成", record)
                    self.assertNotIn("已通过", record)
                    self.assertNotIn("计算成功", record)
                    # 文件清单保持可审查，不额外生成自动启动求解的脚本。
                    self.assertEqual(
                        {path.name for path in folder.iterdir()},
                        {"user.inp", "reference.inp", INPUTS[lab][2],
                         "README.md", "verification.md"},
                    )

    def test_reexport_preserves_a_filled_verification_record(self):
        """已有记录属于用户，再次导出报错后也不能覆盖记录。"""
        with tempfile.TemporaryDirectory() as tmp:
            folder = export_lab("disp_ramp", Path(tmp) / "lab")
            record = folder / "verification.md"
            record.write_text("用户填写的实际验证证据", encoding="utf-8")
            before = {path.name: path.read_bytes() for path in folder.iterdir()}
            with self.assertRaises(FileExistsError):
                export_lab("disp_ramp", folder)
            self.assertEqual(
                {path.name: path.read_bytes() for path in folder.iterdir()}, before
            )

    def test_cli_export_creates_lab(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "from_cli"
            self.assertEqual(main(["subroutine-lab", "--model", "disp_ramp",
                                   "--output", str(folder)]), 0)
            self.assertTrue((folder / "user.inp").is_file())
            self.assertEqual(main(["subroutine-lab", "--model", "disp_ramp",
                                   "--output", str(folder)]), 1)

    def test_each_lab_exports_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            for lab in LABS:
                folder = Path(tmp) / lab
                export_lab(lab, folder)
                self.assertTrue((folder / "user.inp").is_file())
                self.assertTrue((folder / "reference.inp").is_file())
                self.assertEqual(len(list(folder.glob("*.for"))), 1)
                with self.assertRaises(FileExistsError):
                    export_lab(lab, folder)

    def test_heat_labs_use_thermal_dof_and_right_face(self):
        with tempfile.TemporaryDirectory() as tmp:
            for lab, keyword, reference_keyword in (
                ("dflux_wall", "S4NU", "S4"),
                ("film_wall", "F4NU", "F4"),
            ):
                with self.subTest(lab=lab):
                    folder = export_lab(lab, Path(tmp) / lab)
                    user = (folder / "user.inp").read_text("ascii")
                    reference = (folder / "reference.inp").read_text("ascii")
                    self.assertIn("TYPE=DC3D8", user)
                    self.assertIn("*HEAT TRANSFER, STEADY STATE", user)
                    self.assertIn("1, 11, 11, 20.", user)
                    self.assertIn("1, {0}".format(keyword), user)
                    self.assertIn("1, {0},".format(reference_keyword), reference)
                    self.assertNotIn("NU", reference)
                    self.assertIn("NT, RFL", user)
                    self.assertNotIn("*STATIC", user)

    def test_disp_and_usdfld_references_have_expected_mechanics(self):
        with tempfile.TemporaryDirectory() as tmp:
            disp = export_lab("disp_ramp", Path(tmp) / "disp")
            user = (disp / "user.inp").read_text("ascii")
            reference = (disp / "reference.inp").read_text("ascii")
            self.assertIn("*BOUNDARY, USER\n2, 1, 1, 0.1", user)
            self.assertNotIn("*BOUNDARY, USER", reference)
            self.assertIn("2, 1, 1, 0.1", reference)
            field = export_lab("usdfld_elastic", Path(tmp) / "field")
            self.assertIn("105000., 0.3, 0., 1.", (field / "user.inp").read_text("ascii"))
            self.assertIn("*USER DEFINED FIELD", (field / "user.inp").read_text("ascii"))
            self.assertNotIn("*USER DEFINED FIELD", (field / "reference.inp").read_text("ascii"))
            self.assertIn("105000.", (field / "reference.inp").read_text("ascii"))

    def test_new_labs_have_distinct_user_and_reference_physics(self):
        with tempfile.TemporaryDirectory() as tmp:
            stress = export_lab("uvarm_stress_ratio", Path(tmp) / "stress")
            stress_user = (stress / "user.inp").read_text("ascii")
            stress_ref = (stress / "reference.inp").read_text("ascii")
            self.assertIn("*USER OUTPUT VARIABLES\n1", stress_user)
            self.assertIn("S, E, UVARM", stress_user)
            self.assertNotIn("*USER OUTPUT VARIABLES", stress_ref)

            expansion = export_lab("uexpan_thermal_bar", Path(tmp) / "expansion")
            expansion_user = (expansion / "user.inp").read_text("ascii")
            expansion_ref = (expansion / "reference.inp").read_text("ascii")
            self.assertIn("*EXPANSION, USER", expansion_user)
            self.assertIn("*INITIAL CONDITIONS, TYPE=TEMPERATURE", expansion_user)
            self.assertIn("*TEMPERATURE\n1, 70.\n2, 70.", expansion_user)
            self.assertIn("*EXPANSION\n1.0E-5", expansion_ref)
            self.assertNotIn("*EXPANSION, USER", expansion_ref)

            heat = export_lab("hetval_heated_wall", Path(tmp) / "heat")
            heat_user = (heat / "user.inp").read_text("ascii")
            heat_ref = (heat / "reference.inp").read_text("ascii")
            self.assertIn("*HEAT GENERATION", heat_user)
            self.assertNotIn("*HEAT GENERATION", heat_ref)
            self.assertIn("*DFLUX\n1, BF, 1000.", heat_ref)
            self.assertIn("TYPE=DC3D8", heat_user)

    def test_fixed_form_sources_fit_72_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            for lab in LABS:
                folder = export_lab(lab, Path(tmp) / lab)
                source = next(folder.glob("*.for")).read_text("ascii")
                self.assertTrue(all(len(line) <= 72 for line in source.splitlines()))


if __name__ == "__main__":
    unittest.main()
