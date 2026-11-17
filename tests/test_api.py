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


class FakeDevice:
    def __init__(self):
        self.state = FakeState()
        self._online = True
        self.refreshed = 0
        self.applied = 0
        self.fail = []

    def refresh(self, cloud):
        if self.fail:
            raise self.fail.pop(0)
        self.refreshed += 1

    def apply(self, cloud):
        self.applied += 1


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

    def test_redact_keeps_last_four(self):
        self.assertEqual(api.redact(FAKE_ID), "***9012")
        self.assertEqual(api.redact("ab"), "***")

    def test_unknown_region(self):
        with self.assertRaises(ValueError):
            api.AristonDeosApi("xx", "a", "b")


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
