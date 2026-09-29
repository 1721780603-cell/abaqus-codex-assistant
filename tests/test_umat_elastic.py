"""Offline checks; these do not replace Fortran/Abaqus verification."""
import json
import math
from pathlib import Path
import tempfile
import unittest

from abaqus_codex.configuration import validate_config, ConfigurationError
from abaqus_codex.user_subroutine import prepare_user_subroutine
from abaqus_codex.workflow import _abaqus_script_for_config
from abaqus_codex.report import build_chinese_report

ROOT = Path(__file__).resolve().parents[1]


class UmatTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'configs/umat_elastic.json').read_text())

    def test_default_and_dispatch(self):
        config = validate_config(self.config)
        self.assertEqual(config['model']['type'], 'umat_elastic')
        self.assertTrue(_abaqus_script_for_config(config).is_file())
        self.assertEqual(config['analysis']['right_edge_displacement'], .001)

    def test_rejects_nonfinite_input(self):
        for bad in (math.inf, -math.inf, math.nan):
            with self.subTest(value=bad):
                self.config['material']['youngs_modulus'] = bad
                with self.assertRaises(ConfigurationError):
                    validate_config(self.config)

    def test_limits(self):
        for group, key, value in [('analysis', 'right_edge_displacement', .1),
                                  ('material', 'poisson_ratio', .49),
                                  ('model', 'thickness', 1),
                                  ('units', 'length', 'm')]:
            with self.subTest(key=key):
                config = json.loads(json.dumps(self.config))
                config[group][key] = value
                with self.assertRaises(ConfigurationError):
                    validate_config(config)

    def test_fixed_source_packaging(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = prepare_user_subroutine(validate_config(self.config), Path(tmp))
            self.assertEqual(source.name, 'elastic_umat.for')
            text = source.read_text(encoding='ascii')
            # Fixed-form Fortran must not silently truncate executable lines.
            self.assertTrue(all(len(line) <= 72 for line in text.splitlines()
                                if not line.startswith('C')))
            self.assertNotIn('@', text)

    def test_report_uses_measured_values_and_comparison(self):
        data = dict(config=validate_config(self.config), maximum_displacement=.00104,
                    maximum_mises_stress=3.001, mean_s11=3.001, theoretical_s11=3,
                    right_rf1=300.1, left_rf1=-300.1, theoretical_reaction=300,
                    relative_s11_error=.000333, relative_reference_error=.000333,
                    relative_reaction_error=.000333, relative_balance_error=0,
                    odb_path='umat.odb', reference={'odb_path':'reference.odb'},
                    user_subroutine='elastic_umat.for')
        report = build_chinese_report(data)
        self.assertIn('3.001', report)
        self.assertIn('reference.odb', report)
        self.assertNotIn('二维平面应力', report)


if __name__ == '__main__':
    unittest.main()
