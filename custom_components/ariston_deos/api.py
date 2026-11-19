"""Thin wrapper over midea-beautiful-air, sending commands through the cloud.

No Home Assistant imports here so it can be unit tested. Everything blocks:
call it from an executor. The cloud path is used because the Ariston app is
the Midea family app and the local token and key cannot be fetched for it.
"""

from __future__ import annotations

import logging
import re
import threading
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

# One-button settings for the household, from the Deos 16S NET manual's four modes:
# Laundry (mode 4) runs the fan at maximum and sets humidity by itself, Auto (3) holds
# 45 to 55 percent by the room temperature, Continuous (2) dries at full power until the
# tank is full. The mode numbers are the Midea convention, NOT verified on a live Deos;
# the probe must confirm them before these are trusted.
PRESETS: dict[str, dict[str, Any]] = {
    "laundry": {"power": True, "mode": 4},
    "everyday": {"power": True, "mode": 3},
    "boost": {"power": True, "mode": 2},
    "off": {"power": False},
}

MIN_HUMIDITY = 35
MAX_HUMIDITY = 85
HUMIDITY_STEP = 5


# --- Log scrubbing for the library's own loggers ------------------------------
#
# midea_beautiful logs appliance ids, tokens, keys and raw packets at DEBUG from
# loggers we do not own. A logger filter on the parent does not see records of
# child loggers, so the filter is also run from the record factory, which every
# record passes through, including those of loggers created later. It works
# from import time, before the first request.

_LIB_LOGGER = "midea_beautiful"
_SECRETS: set[str] = set()
_MASK = "***"
_PATTERNS = [
    # raw packets: b'...' / b"..." / bytearray(b'...')
    (re.compile(r"""\b(?:bytearray\()?b(['"]).*?(?<!\\)\1\)?""", re.S), "<packet>"),
    # key: value pairs that carry credentials
    (
        re.compile(
            r"""(?i)(['"]?(?:token|key|password|passwd|secret|sign|accesstoken|"""
            r"""accountname|account|loginaccount|session\w*|udpid|sn|mac)['"]?\s*[:=]\s*)"""
            r"""(?:'[^']*'|"[^"]*"|[^\s,}\]]+)"""
        ),
        r"\1" + _MASK,
    ),
    (re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"), _MASK),  # e-mail account
    (re.compile(r"\b[0-9A-Fa-f]{16,}\b"), _MASK),  # keys, tokens, hex packets
    (re.compile(r"\b\d{6,}\b"), _MASK),  # appliance ids
    (re.compile(r"\b[A-Za-z0-9+/_-]{24,}={0,2}"), _MASK),  # base64-ish blobs
]


def register_secret(value: Any) -> None:
    """Make the log filter mask an exact string (account, password)."""
    text = str(value or "")
    if len(text) >= 3:
        _SECRETS.add(text)


def scrub(text: str) -> str:
    """Mask anything in a library log line that could identify or unlock."""
    for secret in _SECRETS:
        text = text.replace(secret, _MASK)
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    return text


class _MideaLogFilter(logging.Filter):
    """Rewrite midea_beautiful records in place so no handler sees raw data."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != _LIB_LOGGER and not record.name.startswith(_LIB_LOGGER + "."):
            return True
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 a bad format string must not leak args
            message = str(record.msg)
        record.msg = scrub(message)
        record.args = None
        # Tracebacks can embed packets or ids: keep only the exception name.
        if record.exc_info:
            exc = record.exc_info[1]
            record.msg += f" ({type(exc).__name__})"
        record.exc_info = None
        record.exc_text = None
        return True


_LOG_FILTER = _MideaLogFilter()


def install_log_filter() -> None:
    """Install the scrubber once. Safe to call any number of times."""
    logging.getLogger(_LIB_LOGGER).addFilter(_LOG_FILTER)  # no-op if present
    factory = logging.getLogRecordFactory()
    if getattr(factory, "_ariston_deos_scrub", False):
        return

    def scrubbing_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = factory(*args, **kwargs)
        _LOG_FILTER.filter(record)
        return record

    scrubbing_factory._ariston_deos_scrub = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(scrubbing_factory)


install_log_filter()


# Offsets in the status payload the library hands to process_response().
_MIN_STATUS_LEN = 19  # the parser reads up to index 18
_TANK_WARNING_BYTE = 15


def _apply_keeping_tank_warning(dev: Any, cloud: Any, warning: int) -> None:
    """dev.apply(), but the write carries the tank warning level the device reported.

    The library parses tank_warning_level from the status reply yet does not
    keep it on the appliance, and its set command then writes 0. Wrap the
    command builder for this one call only; the library is not modified.
    """
    state = dev.state
    build = state.apply_command

    def build_with_warning() -> Any:
        cmd = build()
        cmd.tank_warning_level = warning
        return cmd

    state.apply_command = build_with_warning
    try:
        dev.apply(cloud)
    finally:
        del state.apply_command  # back to the class method


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


def _is_dehumidifier_type(value: Any) -> bool:
    """True for 0xa1 in any spelling: "0xA1", "a1", 161 or the signed byte -95."""
    text = str(value).strip().lower()
    try:
        if text.startswith(("0x", "-0x")):
            number = int(text, 16)
        elif re.fullmatch(r"-?\d+", text):
            number = int(text)
        else:
            number = int(text, 16)
    except ValueError:
        return False
    if number < 0:
        number += 256  # signed byte
    return number == 0xA1


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
        register_secret(account)
        register_secret(password)
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
            if _is_dehumidifier_type(item.get("type", "")):
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

    @staticmethod
    def _fresh_refresh(dev: Any, cloud: Any) -> int:
        """Refresh and prove a status payload really arrived.

        The library ignores an unsupported or empty reply and leaves the old
        (or default) values in place, so a bare refresh() proves nothing.
        Clear the raw payload first and require a new one afterwards.
        Returns the tank warning level the device reported.
        """
        dev.state.latest_data = b""
        dev.refresh(cloud)
        data = getattr(dev.state, "latest_data", b"")
        if not isinstance(data, (bytes, bytearray)) or len(data) < _MIN_STATUS_LEN:
            raise AristonCloudError("Cloud returned no usable status")
        return int(data[_TANK_WARNING_BYTE])

    def query_state(self, appliance_id: str) -> DeosState:
        """Send the status command through the cloud and parse the reply."""
        dev = self._device(appliance_id)
        _LOGGER.debug("Query %s", redact(appliance_id))
        self._call(lambda c: self._fresh_refresh(dev, c))
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
            warning = self._fresh_refresh(dev, cloud)
            st = dev.state
            if "power" in changes:
                st.running = bool(changes["power"])
            if "mode" in changes:
                st.mode = int(changes["mode"])
            if "target_humidity" in changes:
                st.target_humidity = int(changes["target_humidity"])
            if "fan_speed" in changes:
                st.fan_speed = int(changes["fan_speed"])
            _apply_keeping_tank_warning(dev, cloud, warning)

        self._call(run)
        return self._read(dev)
