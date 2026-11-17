"""Unit tests for the pure parts of probe.py. Run: python3 -m unittest scripts.test_probe"""

import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import probe  # noqa: E402


class MaskTests(unittest.TestCase):
    def test_masks_all_but_last_four(self):
        self.assertEqual(probe.mask_id("123456789"), "*****6789")

    def test_short_and_empty(self):
        self.assertEqual(probe.mask_id("123"), "***")
        self.assertEqual(probe.mask_id(None), "")


class TypeTests(unittest.TestCase):
    def test_dehumidifier_spellings(self):
        for value in ("0xA1", "a1", "0xa1", 161, -95, "161"):
            self.assertTrue(probe.is_dehumidifier(value), value)

    def test_others(self):
        for value in ("0xAC", 172, "", None):
            self.assertFalse(probe.is_dehumidifier(value), value)


class UdpTests(unittest.TestCase):
    def test_two_candidates_of_32_hex(self):
        ids = probe.udp_ids("12345678901234")
        self.assertEqual(len(ids), 2)
        for value in ids:
            self.assertEqual(len(value), 32)
            int(value, 16)

    def test_matches_library_when_installed(self):
        try:
            from midea_beautiful.lan import _get_udp_id
        except ImportError:
            self.skipTest("midea_beautiful not installed")
        n = 12345678901234
        self.assertEqual(probe.udp_id(n, "little"), _get_udp_id(n.to_bytes(6, "little")))
        self.assertEqual(probe.udp_id(n, "big"), _get_udp_id(n.to_bytes(6, "big")))


class ErrorTextTests(unittest.TestCase):
    def test_carries_code_not_secret(self):
        class Boom(Exception):
            error_code = 9999
            message = "system error for me@example.com"

        probe._SECRETS[:] = ["me@example.com"]
        text = probe.error_text(Boom())
        probe._SECRETS[:] = []
        self.assertIn("9999", text)
        self.assertNotIn("me@example.com", text)


class VerdictTests(unittest.TestCase):
    def test_no_login(self):
        out = probe.verdict([probe.RegionResult("EU"), probe.RegionResult("US")])
        self.assertEqual(len(out), 1)
        self.assertIn("no region accepted", out[0])

    def test_no_dehumidifier(self):
        out = probe.verdict([probe.RegionResult("EU", login=True)])
        self.assertIn("no dehumidifier", out[-1])

    def test_eu_token_and_status(self):
        r = probe.RegionResult("EU", login=True, dehumidifiers=1, token=True, status=True)
        out = " ".join(probe.verdict([probe.RegionResult("US"), r]))
        self.assertIn("token route WORKS on EU", out)
        self.assertIn("cloud status WORKS on EU", out)

    def test_token_fails_status_works(self):
        r = probe.RegionResult("EU", login=True, dehumidifiers=1, status=True)
        out = " ".join(probe.verdict([r]))
        self.assertIn("local token route FAILS", out)
        self.assertIn("cloud status WORKS", out)


class KeyFileTests(unittest.TestCase):
    def test_mode_600(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.keys")
            probe.write_keys(path, "tok", "key")
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
