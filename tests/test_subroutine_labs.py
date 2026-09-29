"""Offline checks for the fixed teaching input decks."""
from pathlib import Path
import tempfile
import unittest

from abaqus_codex.subroutine_labs import LABS, export_lab
from abaqus_codex.cli import main


class SubroutineLabTests(unittest.TestCase):
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
