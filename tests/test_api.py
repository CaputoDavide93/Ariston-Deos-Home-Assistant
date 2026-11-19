"""Tests for the pure api layer. No Home Assistant import, no network."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

_PATH = pathlib.Path(__file__).parent.parent / "custom_components" / "ariston_deos" / "api.py"
_spec = importlib.util.spec_from_file_location("deos_api", _PATH)
api = importlib.util.module_from_spec(_spec)
sys.modules["deos_api"] = api
_spec.loader.exec_module(api)

try:
    import midea_beautiful  # noqa: F401

    HAVE_LIB = True
except ImportError:
    HAVE_LIB = False

FAKE_ID = "123456789012"


class CloudAuthenticationError(Exception):
    """Same class name as the library's, to test mapping by name."""


class FakeState:
    running = False
    mode = 1
    target_humidity = 50
    current_humidity = 61
    fan_speed = 40
    tank_full = False
    _error = 0
    latest_data = b""

    def apply_command(self):
        return FakeCmd()


class FakeCmd:
    tank_warning_level = 0


def status_payload(warning=0):
    p = bytearray(22)
    p[15] = warning
    return bytes(p)


class FakeDevice:
    def __init__(self):
        self.state = FakeState()
        self._online = True
        self.refreshed = 0
        self.applied = 0
        self.fail = []
        self.warning = 75
        self.reply = True  # False: library ignores the reply, keeps old data
        self.sent_cmds = []

    def refresh(self, cloud):
        if self.fail:
            raise self.fail.pop(0)
        self.refreshed += 1
        if self.reply:
            self.state.latest_data = status_payload(self.warning)

    def apply(self, cloud):
        self.applied += 1
        self.sent_cmds.append(self.state.apply_command())


class FakeCloud:
    def list_appliances(self, force=False):
        return [
            {"id": FAKE_ID, "name": "Deos", "type": "0xa1"},
            {"id": "999", "name": "Aircon", "type": "0xac"},
        ]


def make(devices=None, connect=None):
    dev = FakeDevice()
    connects = []

    def _connect(region, account, password):
        connects.append(region)
        if connect:
            connect()
        return FakeCloud()

    client = api.AristonDeosApi(
        "eu", "a@example.invalid", "fake-pass", connect=_connect, device_factory=lambda i: dev
    )
    return client, dev, connects


class ApiLogicTests(unittest.TestCase):
    def test_lists_only_dehumidifiers(self):
        client, _, _ = make()
        found = client.list_dehumidifiers()
        self.assertEqual([d.appliance_id for d in found], [FAKE_ID])

    def test_query_state_maps_fields(self):
        client, dev, _ = make()
        st = client.query_state(FAKE_ID)
        self.assertEqual((st.target_humidity, st.current_humidity, st.mode), (50, 61, 1))
        self.assertFalse(st.power)
        self.assertEqual(dev.refreshed, 1)

    def test_set_refreshes_first_then_applies(self):
        client, dev, _ = make()
        st = client.set(FAKE_ID, power=True, target_humidity=55, mode=3)
        self.assertEqual((dev.refreshed, dev.applied), (1, 1))
        self.assertTrue(st.power)
        self.assertEqual((st.target_humidity, st.mode), (55, 3))

    def test_set_rejects_bad_values(self):
        client, _, _ = make()
        for bad in ({"target_humidity": 20}, {"target_humidity": 90}, {"mode": 9}, {"volume": 1}):
            with self.assertRaises(ValueError):
                client.set(FAKE_ID, **bad)

    def test_relogin_once_on_auth_error(self):
        client, dev, connects = make()
        client.login()
        dev.fail = [CloudAuthenticationError("x")]
        client.query_state(FAKE_ID)
        self.assertEqual(len(connects), 2)

    def test_second_auth_error_maps_to_auth_error(self):
        client, dev, _ = make()
        dev.fail = [CloudAuthenticationError("x"), CloudAuthenticationError("x")]
        with self.assertRaises(api.AristonCloudAuthError):
            client.query_state(FAKE_ID)

    def test_other_errors_map_to_cloud_error_without_relogin(self):
        client, dev, connects = make()
        client.login()
        dev.fail = [OSError("boom")]
        with self.assertRaises(api.AristonCloudError) as ctx:
            client.query_state(FAKE_ID)
        self.assertNotIsInstance(ctx.exception, api.AristonCloudAuthError)
        self.assertEqual(len(connects), 1)

    def test_login_failure_mapping(self):
        def bad():
            raise CloudAuthenticationError("secret-leak")

        client, _, _ = make(connect=bad)
        with self.assertRaises(api.AristonCloudAuthError) as ctx:
            client.login()
        self.assertNotIn("secret-leak", str(ctx.exception))

    def test_unsupported_reply_is_an_error_not_cached_success(self):
        client, dev, _ = make()
        dev.reply = False
        with self.assertRaises(api.AristonCloudError):
            client.query_state(FAKE_ID)
        with self.assertRaises(api.AristonCloudError):
            client.set(FAKE_ID, power=True)
        self.assertEqual(dev.applied, 0)  # nothing written from default state

    def test_stale_payload_from_earlier_poll_does_not_count(self):
        client, dev, _ = make()
        client.query_state(FAKE_ID)  # good poll leaves latest_data behind
        dev.reply = False
        with self.assertRaises(api.AristonCloudError):
            client.query_state(FAKE_ID)

    def test_set_keeps_reported_tank_warning_level(self):
        client, dev, _ = make()
        client.set(FAKE_ID, power=True)
        self.assertEqual(dev.sent_cmds[0].tank_warning_level, 75)
        self.assertNotIn("apply_command", vars(dev.state))  # wrapper removed

    def test_discovery_accepts_every_spelling_of_a1(self):
        for kind in ("0xA1", "a1", "A1", "161", 161, "-95", -95, "0xa1"):
            self.assertTrue(api._is_dehumidifier_type(kind), kind)
        for kind in ("0xac", "ac", "172", "-84", "", None, "zz", "417"):
            self.assertFalse(api._is_dehumidifier_type(kind), kind)

    def test_discovery_finds_signed_type(self):
        client, _, _ = make()
        client._connect = lambda *a: type(
            "C", (), {"list_appliances": lambda self, f=False: [
                {"id": FAKE_ID, "name": "Deos", "type": "-95"}]}
        )()
        self.assertEqual([d.appliance_id for d in client.list_dehumidifiers()], [FAKE_ID])

    def test_redact_keeps_last_four(self):
        self.assertEqual(api.redact(FAKE_ID), "***9012")
        self.assertEqual(api.redact("ab"), "***")

    def test_unknown_region(self):
        with self.assertRaises(ValueError):
            api.AristonDeosApi("xx", "a", "b")


class LogFilterTests(unittest.TestCase):
    def _capture(self, name, msg, *args, **kw):
        import logging

        records = []

        class H(logging.Handler):
            def emit(self, record):
                records.append(record)

        log = logging.getLogger(name)
        h = H()
        old = log.level
        log.setLevel(logging.DEBUG)
        log.addHandler(h)
        try:
            log.debug(msg, *args, **kw)
        finally:
            log.removeHandler(h)
            log.setLevel(old)
        return records[0].getMessage(), records[0]

    def test_child_logger_record_is_masked_before_first_request(self):
        api.register_secret("someone@example.invalid")
        api.register_secret("fake-pass")
        msg, rec = self._capture(
            "midea_beautiful.lan",
            "Packet for %s data: %s acct=%s %s",
            FAKE_ID, b"\x5a\x5a\x01\x11" + b"\x00" * 8,
            "someone@example.invalid", {"token": "abcdef0123456789abcdef", "id": FAKE_ID},
        )
        for leak in (FAKE_ID, "x5a", "someone@example", "abcdef0123456789"):
            self.assertNotIn(leak, msg)
        self.assertIsNone(rec.args)

    def test_traceback_is_dropped(self):
        try:
            raise OSError(FAKE_ID)
        except OSError:
            msg, rec = self._capture("midea_beautiful.cloud", "boom", exc_info=True)
        self.assertIsNone(rec.exc_info)
        self.assertNotIn(FAKE_ID, msg)

    def test_other_loggers_untouched_and_install_idempotent(self):
        import logging

        api.install_log_filter()
        api.install_log_filter()
        msg, _ = self._capture("other.logger", "id %s", FAKE_ID)
        self.assertIn(FAKE_ID, msg)
        f = logging.getLogger("midea_beautiful").filters
        self.assertEqual(f.count(api._LOG_FILTER), 1)
        factory = logging.getLogRecordFactory()
        self.assertFalse(getattr(factory.__closure__[0].cell_contents, "_ariston_deos_scrub", False))


@unittest.skipUnless(HAVE_LIB, "midea-beautiful-air not installed")
class LibraryBytesTests(unittest.TestCase):
    """Run the real library command and parser against a fake cloud."""

    @staticmethod
    def reply(run=1, mode=3, target=55, fan=60, tank=0, current=63, err=0):
        p = bytearray(22)
        p[0] = 0xC8
        p[1] = run
        p[2] = mode
        p[3] = fan
        p[7] = target
        p[10] = tank
        p[16] = current
        p[17] = 90  # 20 C
        p[21] = err
        return bytes([0xAA, 0, 0xA1, 0, 0, 0, 0, 0, 0, 3]) + bytes(p)

    class Cloud:
        def __init__(self, reply):
            self.sent = []
            self._reply = reply

        def appliance_transparent_send(self, appliance_id, data):
            self.sent.append(data)
            return [self._reply]

    def make(self, **kw):
        cloud = self.Cloud(self.reply(**kw))
        client = api.AristonDeosApi(
            "eu", "a@example.invalid", "fake-pass", connect=lambda *a: cloud
        )
        return client, cloud

    def test_status_reply_parsed(self):
        client, cloud = self.make(run=1, mode=3, target=55, fan=60, tank=100, current=63)
        st = client.query_state(FAKE_ID)
        self.assertTrue(st.power)
        self.assertEqual((st.mode, st.target_humidity, st.fan_speed), (3, 55, 60))
        self.assertTrue(st.tank_full)
        self.assertEqual(st.current_humidity, 63)

    def test_status_packet_is_cloud_packet_for_dehumidifier(self):
        client, cloud = self.make()
        client.query_state(FAKE_ID)
        pkt = cloud.sent[0]
        self.assertEqual(pkt[:4], bytes([0x5A, 0x5A, 0x01, 0x11]))
        self.assertEqual(int.from_bytes(pkt[20:28], "little"), int(FAKE_ID))
        self.assertEqual(pkt[40:43], bytes([0xAA, 0x20, 0xA1]))  # unencrypted body
        self.assertEqual(pkt[50], 0x41)  # status request

    def test_real_library_keeps_tank_warning_on_power_only_write(self):
        p = bytearray(self.reply(run=0))
        p[10 + 15] = 75  # 10 header bytes, then payload byte 15
        cloud = self.Cloud(bytes(p))
        client = api.AristonDeosApi("eu", "a@example.invalid", "x", connect=lambda *a: cloud)
        client.set(FAKE_ID, power=True)
        body = cloud.sent[1][40:-16]
        self.assertEqual(body[23], 75)

    def test_real_library_unsupported_reply_raises(self):
        bad = bytearray(self.reply())
        bad[9] = 9  # extended reply type the library ignores
        cloud = self.Cloud(bytes(bad))
        client = api.AristonDeosApi("eu", "a@example.invalid", "x", connect=lambda *a: cloud)
        with self.assertRaises(api.AristonCloudError):
            client.set(FAKE_ID, power=True)
        self.assertEqual(len(cloud.sent), 1)  # no write

    def test_set_packet_carries_changes(self):
        client, cloud = self.make(run=0, mode=1, target=50)
        client.set(FAKE_ID, power=True, target_humidity=60, mode=2)
        self.assertEqual(len(cloud.sent), 2)  # refresh, then set
        body = cloud.sent[1][40:-16]
        self.assertEqual(body[2], 0xA1)
        self.assertEqual(body[10], 0x48)  # write
        self.assertEqual(body[11] & 1, 1)  # on
        self.assertEqual(body[12] & 0x0F, 2)  # mode
        self.assertEqual(body[17] & 0x7F, 60)  # target humidity


if __name__ == "__main__":
    unittest.main()


class PresetTests(unittest.TestCase):
    def test_every_preset_is_a_valid_set_call(self) -> None:
        for name, changes in api.PRESETS.items():
            self.assertTrue(set(changes) <= {"power", "mode", "target_humidity", "fan_speed"}, name)
            if "mode" in changes:
                self.assertIn(changes["mode"], api.MODES, name)
            if "target_humidity" in changes:
                self.assertTrue(api.MIN_HUMIDITY <= changes["target_humidity"] <= api.MAX_HUMIDITY, name)

    def test_the_presets_the_household_needs_exist(self) -> None:
        self.assertEqual(set(api.PRESETS), {"laundry", "everyday", "boost", "off"})
        self.assertEqual(api.PRESETS["laundry"]["mode"], 4)  # clothes drying
        self.assertIs(api.PRESETS["off"]["power"], False)
        for name in ("laundry", "everyday", "boost"):
            self.assertIs(api.PRESETS[name]["power"], True, f"{name} must switch the unit on")
