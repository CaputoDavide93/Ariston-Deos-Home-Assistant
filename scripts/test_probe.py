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
    def test_code_only_never_message(self):
        class Boom(Exception):
            error_code = 9999
            message = "token abc123 for me@example.com id 99887766"

        text = probe.error_text(Boom("secret-key-xyz"))
        self.assertEqual(text, "Boom (code 9999)")

    def test_invalid_code_dropped(self):
        class Bad(Exception):
            error_code = "tok-123"

        self.assertEqual(probe.error_text(Bad("x")), "Bad")
        Bad.error_code = True
        self.assertEqual(probe.error_text(Bad("x")), "Bad")


class StatusTests(unittest.TestCase):
    def test_default_state_is_not_a_status(self):
        class State:
            latest_data = b""

        self.assertFalse(probe.status_received(State()))
        State.latest_data = b"\xc8\x01"
        self.assertTrue(probe.status_received(State()))
        self.assertFalse(probe.status_received(State(), responses_ok=False))


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


class DiscoveryTests(unittest.TestCase):
    def test_failed_discovery_is_undetermined(self):
        out = " ".join(probe.verdict([probe.RegionResult("EU", login=True, discovery_failed=True)]))
        self.assertIn("undetermined", out)
        self.assertNotIn("is on the account", out)


class KeyFileTests(unittest.TestCase):
    def test_mode_600(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.keys")
            probe.write_keys(path, "tok", "key")
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_existing_file_refused_without_force(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.keys")
            with open(path, "w") as h:
                h.write("old")
            os.chmod(path, 0o644)
            with self.assertRaises(FileExistsError):
                probe.write_keys(path, "tok", "key")
            probe.write_keys(path, "tok", "key", force=True)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertIn("token=tok", open(path).read())

    def test_symlink_refused_even_with_force(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "t")
            link = os.path.join(d, "l")
            open(target, "w").close()
            os.symlink(target, link)
            with self.assertRaises(OSError):
                probe.write_keys(link, "tok", "key", force=True)
            self.assertEqual(open(target).read(), "")


class CredentialTests(unittest.TestCase):
    def test_prompts_are_hidden(self):
        from unittest import mock

        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
            probe.getpass, "getpass", side_effect=["a@b.c", "pw"]
        ) as gp, mock.patch("builtins.input", side_effect=AssertionError):
            self.assertEqual(probe.get_credentials(), ("a@b.c", "pw"))
            self.assertEqual(gp.call_count, 2)


if __name__ == "__main__":
    unittest.main()
