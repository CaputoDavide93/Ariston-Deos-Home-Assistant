"""Thin wrapper over midea-beautiful-air, sending commands through the cloud.

No Home Assistant imports here so it can be unit tested. Everything blocks:
call it from an executor. The cloud path is used because the Ariston app is
the Midea family app and the local token and key cannot be fetched for it.
"""

from __future__ import annotations

import threading

import logging
from dataclasses import dataclass
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)

# Library app names per region (see midea_beautiful.midea.SUPPORTED_APPS).
REGION_APPS = {"eu": "Ariston Clima EU", "us": "Ariston Clima"}

DEHUMIDIFIER_TYPE = "0xa1"

# Mode numbers follow the Midea dehumidifier convention. The library only
# range checks them (0 to 15); these names are NOT verified on a live device.
MODES: dict[int, str] = {1: "set", 2: "continuous", 3: "smart", 4: "dry"}
FAN_SPEEDS: dict[str, int] = {"low": 40, "medium": 60, "high": 80}

MIN_HUMIDITY = 35
MAX_HUMIDITY = 85
HUMIDITY_STEP = 5


class AristonCloudError(Exception):
    """The cloud could not be reached or answered badly."""


class AristonCloudAuthError(AristonCloudError):
    """The cloud refused the account or password."""


@dataclass
class DeosState:
    """One reading of the dehumidifier."""

    power: bool
    mode: int
    target_humidity: int
    current_humidity: int
    fan_speed: int
    tank_full: bool
    error_code: int
    online: bool = True


@dataclass
class DeosDevice:
    """A dehumidifier found on the account."""

    appliance_id: str
    name: str


def redact(value: Any) -> str:
    """Keep only the last 4 characters, so logs never carry a full id."""
    text = str(value)
    return "***" + text[-4:] if len(text) > 4 else "***"


def _classify(exc: Exception) -> AristonCloudError:
    """Map any library or network exception to our own, without importing it."""
    names = {c.__name__ for c in type(exc).__mro__}
    if names & {"CloudAuthenticationError", "AuthenticationError"}:
        return AristonCloudAuthError("Cloud refused the login")
    return AristonCloudError(f"Cloud call failed ({type(exc).__name__})")


def _default_connect(region: str, account: str, password: str) -> Any:
    from midea_beautiful import connect_to_cloud  # lazy: heavy, HA installs it

    return connect_to_cloud(
        account=account, password=password, appname=REGION_APPS[region]
    )


def _default_device(appliance_id: str) -> Any:
    from midea_beautiful.lan import LanDevice

    return LanDevice(appliance_id=appliance_id, appliance_type=DEHUMIDIFIER_TYPE)


class AristonDeosApi:
    """Blocking client for one account."""

    def __init__(
        self,
        region: str,
        account: str,
        password: str,
        connect: Callable[[str, str, str], Any] = _default_connect,
        device_factory: Callable[[str], Any] = _default_device,
    ) -> None:
        if region not in REGION_APPS:
            raise ValueError("Unknown region")
        self._region = region
        self._account = account
        self._password = password
        self._connect = connect
        self._device_factory = device_factory
        self._cloud: Any = None
        self._devices: dict[str, Any] = {}
        # One cloud call at a time: the library keeps session state and sequence
        # numbers, and the account must not be hammered (Codex review, 17 Nov 2026).
        self._lock = threading.RLock()

    def login(self) -> None:
        """(Re)build the cloud session."""
        try:
            self._cloud = self._connect(self._region, self._account, self._password)
        except Exception as exc:  # noqa: BLE001
            raise _classify(exc) from None
        self._devices.clear()

    def _call(self, fn: Callable[[Any], Any]) -> Any:
        """Run a cloud call, logging in once more on an auth failure."""
        with self._lock:
            return self._call_locked(fn)

    def _call_locked(self, fn: Callable[[Any], Any]) -> Any:
        if self._cloud is None:
            self.login()
        try:
            return fn(self._cloud)
        except Exception as exc:  # noqa: BLE001
            err = _classify(exc)
            if not isinstance(err, AristonCloudAuthError):
                raise err from None
        _LOGGER.debug("Session rejected, logging in again")
        self.login()
        try:
            return fn(self._cloud)
        except Exception as exc:  # noqa: BLE001
            raise _classify(exc) from None

    def list_dehumidifiers(self) -> list[DeosDevice]:
        """Dehumidifiers (type 0xA1) on the account."""
        items = self._call(lambda c: c.list_appliances(True))
        found = []
        for item in items or []:
            kind = str(item.get("type", "")).lower()
            if kind in ("0xa1", "a1", "161"):
                found.append(
                    DeosDevice(str(item["id"]), item.get("name") or "Ariston Deos")
                )
        return found

    def _device(self, appliance_id: str) -> Any:
        if appliance_id not in self._devices:
            self._devices[appliance_id] = self._device_factory(appliance_id)
        return self._devices[appliance_id]

    @staticmethod
    def _read(dev: Any) -> DeosState:
        s = dev.state
        return DeosState(
            power=bool(s.running),
            mode=int(s.mode),
            target_humidity=int(s.target_humidity),
            current_humidity=int(s.current_humidity),
            fan_speed=int(s.fan_speed),
            tank_full=bool(s.tank_full),
            error_code=int(s._error),  # noqa: SLF001 no public accessor
            online=bool(getattr(dev, "_online", True)),
        )

    def query_state(self, appliance_id: str) -> DeosState:
        """Send the status command through the cloud and parse the reply."""
        dev = self._device(appliance_id)
        _LOGGER.debug("Query %s", redact(appliance_id))
        self._call(lambda c: dev.refresh(c))
        return self._read(dev)

    def set(self, appliance_id: str, **changes: Any) -> DeosState:
        """Apply power, mode, target_humidity or fan_speed changes.

        The library's set command rewrites the whole state, so refresh first
        or defaults would overwrite what the device is really doing.
        """
        allowed = {"power", "mode", "target_humidity", "fan_speed"}
        if set(changes) - allowed:
            raise ValueError("Unknown setting")
        if "mode" in changes and int(changes["mode"]) not in MODES:
            raise ValueError("Unknown mode")
        if "target_humidity" in changes:
            h = int(changes["target_humidity"])
            if not MIN_HUMIDITY <= h <= MAX_HUMIDITY:
                raise ValueError("Humidity out of range")
        dev = self._device(appliance_id)
        _LOGGER.debug("Set %s keys=%s", redact(appliance_id), sorted(changes))

        def run(cloud: Any) -> None:
            dev.refresh(cloud)
            st = dev.state
            if "power" in changes:
                st.running = bool(changes["power"])
            if "mode" in changes:
                st.mode = int(changes["mode"])
            if "target_humidity" in changes:
                st.target_humidity = int(changes["target_humidity"])
            if "fan_speed" in changes:
                st.fan_speed = int(changes["fan_speed"])
            dev.apply(cloud)

        self._call(run)
        return self._read(dev)
