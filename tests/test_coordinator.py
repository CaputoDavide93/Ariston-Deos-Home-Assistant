"""Coordinator auth handling, with Home Assistant stubbed out (not installed here)."""

from __future__ import annotations

import asyncio
import importlib
import pathlib
import sys
import types
import unittest

PKG = pathlib.Path(__file__).parent.parent / "custom_components" / "ariston_deos"


class HomeAssistantError(Exception):
    pass


class ConfigEntryAuthFailed(Exception):
    pass


class UpdateFailed(Exception):
    pass


class DataUpdateCoordinator:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, logger, *, config_entry, name, update_interval):
        self.hass = hass
        self.config_entry = config_entry
        self.last_update_success = True
        self.listeners = 0
        self.updated = None
        self.refreshes = 0

    def async_update_listeners(self):
        self.listeners += 1

    def async_set_updated_data(self, data):
        self.updated = data

    async def async_request_refresh(self):
        self.refreshes += 1


def _load():
    stubs = {
        "homeassistant": {},
        "homeassistant.config_entries": {"ConfigEntry": object},
        "homeassistant.core": {"HomeAssistant": object},
        "homeassistant.exceptions": {
            "ConfigEntryAuthFailed": ConfigEntryAuthFailed,
            "HomeAssistantError": HomeAssistantError,
        },
        "homeassistant.helpers": {},
        "homeassistant.helpers.update_coordinator": {
            "DataUpdateCoordinator": DataUpdateCoordinator,
            "UpdateFailed": UpdateFailed,
        },
    }
    for name, attrs in stubs.items():
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        sys.modules[name] = mod
    pkg = types.ModuleType("ariston_deos_under_test")
    pkg.__path__ = [str(PKG)]
    sys.modules["ariston_deos_under_test"] = pkg
    return importlib.import_module("ariston_deos_under_test.coordinator")


coord = _load()
api = sys.modules["ariston_deos_under_test.api"]


class Entry:
    data = {"appliance_id": "123456789012"}

    def __init__(self):
        self.reauth = []

    def async_start_reauth(self, hass):
        self.reauth.append(hass)


class Hass:
    async def async_add_executor_job(self, fn, *args):
        return fn(*args)


class FakeApi:
    def __init__(self, exc):
        self.exc = exc

    def set(self, appliance_id, **changes):
        raise self.exc

    def query_state(self, appliance_id):
        raise self.exc


def make(exc):
    entry = Entry()
    c = coord.AristonDeosCoordinator(Hass(), entry, FakeApi(exc), 60)
    return c, entry


class CoordinatorAuthTests(unittest.TestCase):
    def test_set_auth_failure_starts_reauth_and_raises_service_error(self):
        c, entry = make(api.AristonCloudAuthError("refused"))
        with self.assertRaises(HomeAssistantError):
            asyncio.run(c.async_set(power=True))
        self.assertEqual(len(entry.reauth), 1)
        self.assertFalse(c.last_update_success)
        self.assertEqual(c.listeners, 1)
        self.assertEqual(c.refreshes, 0)

    def test_set_other_failure_does_not_start_reauth(self):
        c, entry = make(api.AristonCloudError("down"))
        with self.assertRaises(HomeAssistantError):
            asyncio.run(c.async_set(power=True))
        self.assertEqual(entry.reauth, [])
        self.assertTrue(c.last_update_success)

    def test_poll_auth_failure_still_raises_config_entry_auth_failed(self):
        c, _ = make(api.AristonCloudAuthError("refused"))
        with self.assertRaises(ConfigEntryAuthFailed):
            asyncio.run(c._async_update_data())


if __name__ == "__main__":
    unittest.main()
