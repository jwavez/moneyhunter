"""Tool voltage normalisation — Task 3 only. No other detail-check behaviour."""
import unittest

from moneyhunter.details import extract_voltages, normalise_voltage, voltage_matches_expected

PASS_18 = ["18", "18v", "18V", "18.0", "18.0v", "18.0V", "18 volt", "18.0 volt", "18-volt", " 18 v "]
FAIL_18 = ["21.6v", "12v", "36v", "18.5v", "1.8v", ""]
GRACE = ["abc", "v", "18..0v", "N/A"]


class VoltageNormalisation(unittest.TestCase):
    def test_must_pass_against_expected_18(self):
        for raw in PASS_18:
            with self.subTest(raw=raw):
                self.assertTrue(voltage_matches_expected(raw, 18))
                self.assertEqual(normalise_voltage(raw), 18.0)

    def test_must_fail_against_expected_18(self):
        for raw in FAIL_18:
            with self.subTest(raw=raw):
                self.assertFalse(voltage_matches_expected(raw, 18))

    def test_must_fail_gracefully_no_exception(self):
        for raw in GRACE:
            with self.subTest(raw=raw):
                self.assertIsNone(normalise_voltage(raw))
                self.assertFalse(voltage_matches_expected(raw, 18))
                self.assertEqual(extract_voltages(raw), [])

    def test_free_text_tokens_keep_decimals_whole(self):
        self.assertEqual(extract_voltages("18.0V bare tool"), [18.0])
        self.assertEqual(extract_voltages("21.6V battery"), [21.6])
        self.assertEqual(extract_voltages("18.0V / 21.6V"), [18.0, 21.6])
        self.assertNotIn(0, extract_voltages("18.0V"))
        self.assertFalse(voltage_matches_expected("21.6V", 18))
        self.assertTrue(voltage_matches_expected("18.0V", 18))


if __name__ == "__main__":
    unittest.main()
