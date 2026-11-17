#!/usr/bin/env python3
"""Read-only diagnostic for an Ariston Deos dehumidifier on the Ariston Clima cloud.

Run it yourself with your own Ariston Clima login:

    python3 scripts/probe.py [--save-keys PATH] [--region EU|US]

Credentials come from ARISTON_EMAIL and ARISTON_PASSWORD, or a hidden prompt.
They are never taken from argv, printed or written to disk. The probe never
sends a set command: it logs in, lists appliances, asks the cloud for a token
and key, and sends one status query.

Needs `pip install midea-beautiful-air` (tested reading 0.10.7). The library is
imported lazily so the pure helpers below can be unit-tested without it.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from dataclasses import dataclass, field
from hashlib import sha256

# Region label -> the library's SUPPORTED_APPS name. EU first: the house is in Scotland.
REGIONS: dict[str, str] = {"EU": "Ariston Clima EU", "US": "Ariston Clima"}
DEHUMIDIFIER_TYPE = 0xA1


# ----- pure helpers (unit-tested) ---------------------------------------------


def mask_id(value: object) -> str:
    """Show only the last 4 characters of an id."""
    text = str(value or "")
    if len(text) <= 4:
        return "*" * len(text)
    return "*" * (len(text) - 4) + text[-4:]


def is_dehumidifier(appliance_type: object) -> bool:
    """True for type 0xA1 however the cloud spells it ('0xA1', 'a1', 161, -95)."""
    if isinstance(appliance_type, int):
        return appliance_type in (DEHUMIDIFIER_TYPE, DEHUMIDIFIER_TYPE - 256)
    return str(appliance_type).strip().lower() in ("a1", "0xa1", "161", "-95")


def udp_id(appliance_id: int | str, byteorder: str) -> str:
    """The id the cloud keys a token on: the library's own derivation.

    sha256 of the appliance id as 6 bytes, then the two 16-byte halves XORed.
    The library tries little-endian, then big-endian.
    """
    digest = sha256(int(appliance_id).to_bytes(6, byteorder)).digest()  # type: ignore[arg-type]
    return bytes(a ^ b for a, b in zip(digest[:16], digest[16:], strict=True)).hex()


def udp_ids(appliance_id: int | str) -> list[str]:
    return [udp_id(appliance_id, "little"), udp_id(appliance_id, "big")]


def error_text(exc: BaseException) -> str:
    """One short line: exception class and the library's error code, never a credential."""
    code = getattr(exc, "error_code", None)
    message = str(getattr(exc, "message", "") or exc)
    # The library's messages carry the Midea error text, not the login, but be safe.
    for secret in _SECRETS:
        if secret and secret in message:
            message = message.replace(secret, "***")
    message = " ".join(message.split())[:160]
    suffix = f" (code {code})" if code is not None else ""
    return f"{type(exc).__name__}: {message}{suffix}"


_SECRETS: list[str] = []


@dataclass
class RegionResult:
    region: str
    login: bool = False
    dehumidifiers: int = 0
    token: bool = False
    status: bool = False
    notes: list[str] = field(default_factory=list)


def verdict(results: list[RegionResult]) -> list[str]:
    """Plain-language verdict lines from the per-region results."""
    lines: list[str] = []
    logged = [r for r in results if r.login]
    if not logged:
        return [
            "VERDICT: no region accepted the login. Check the email and password "
            "in the Ariston Clima app, then run again."
        ]
    names = " and ".join(r.region for r in logged)
    lines.append(f"VERDICT: login works on {names}.")
    holding = [r for r in logged if r.dehumidifiers]
    if not holding:
        lines.append(
            "VERDICT: no dehumidifier (type 0xA1) is on the account in any region "
            "that accepted the login."
        )
        return lines
    where = " and ".join(r.region for r in holding)
    lines.append(f"VERDICT: the dehumidifier is listed on {where}.")
    tokens = [r for r in holding if r.token]
    if tokens:
        lines.append(
            f"VERDICT: local token route WORKS on {tokens[0].region}. Use HA Core "
            "Midea with manual token and key (re-run with --save-keys PATH)."
        )
    else:
        lines.append(
            "VERDICT: local token route FAILS in every region. HA Core Midea cannot "
            "do local control; the cloud path is the fallback."
        )
    statuses = [r for r in holding if r.status]
    if statuses:
        lines.append(
            f"VERDICT: cloud status WORKS on {statuses[0].region}. The cloud path "
            "of this integration can read the device."
        )
    else:
        lines.append("VERDICT: cloud status FAILS in every region.")
    return lines


# ----- probe steps (need the library and the network) -------------------------


def say(step: str, ok: bool, text: str) -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {step}: {text}", flush=True)


def get_credentials() -> tuple[str, str]:
    email = os.environ.get("ARISTON_EMAIL") or input("Ariston Clima email: ").strip()
    password = os.environ.get("ARISTON_PASSWORD") or getpass.getpass(
        "Ariston Clima password (hidden): "
    )
    return email, password


def write_keys(path: str, token: str, key: str) -> None:
    """Create the file with mode 600 from the start, so it is never world-readable."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(f"token={token}\nkey={key}\n")
    os.chmod(path, 0o600)


def probe_region(
    region: str, email: str, password: str, save_keys: str | None
) -> RegionResult:
    from midea_beautiful import connect_to_cloud  # lazy: keeps helpers testable

    result = RegionResult(region)
    app = REGIONS[region]
    step = f"{region} login ({app})"
    try:
        cloud = connect_to_cloud(account=email, password=password, appname=app)
    except Exception as exc:  # noqa: BLE001 - report every failure plainly
        say(step, False, error_text(exc))
        return result
    result.login = True
    say(step, True, "logged in")

    step = f"{region} appliances"
    try:
        appliances = cloud.list_appliances(force=True)
    except Exception as exc:  # noqa: BLE001
        say(step, False, error_text(exc))
        return result
    say(step, True, f"{len(appliances)} appliance(s)")
    dehumidifiers = []
    for item in appliances:
        flag = is_dehumidifier(item.get("type"))
        print(
            f"        type={item.get('type')} name={item.get('name')!r} "
            f"id={mask_id(item.get('id'))}" + ("  <- dehumidifier" if flag else "")
        )
        if flag:
            dehumidifiers.append(item)
    result.dehumidifiers = len(dehumidifiers)
    if not dehumidifiers:
        return result

    target = dehumidifiers[0]
    appliance_id = target["id"]

    step = f"{region} local token"
    token = key = ""
    last_error = ""
    try:
        for candidate in udp_ids(appliance_id):
            try:
                token, key = cloud.get_token(candidate)
            except Exception as exc:  # noqa: BLE001
                last_error = error_text(exc)
                continue
            if token and key:
                break
    except (ValueError, TypeError) as exc:
        last_error = error_text(exc)
    if token and key:
        result.token = True
        say(step, True, f"token and key returned (lengths {len(token)} and {len(key)})")
        if save_keys:
            write_keys(save_keys, token, key)
            print(f"        keys written to {save_keys} (mode 600)")
    else:
        say(step, False, last_error or "the cloud returned no token for the device")

    step = f"{region} cloud status"
    try:
        from midea_beautiful.appliance import DehumidifierAppliance
        from midea_beautiful.command import DehumidifierStatusCommand

        replies = cloud.appliance_transparent_send(
            appliance_id, DehumidifierStatusCommand().finalize()
        )
        appliance = DehumidifierAppliance(appliance_id, "0xA1")
        appliance.process_response_ext(replies)
        if not appliance.latest_data:
            raise ValueError("the reply held no status payload")
        result.status = True
        say(
            step,
            True,
            f"power={'on' if appliance.running else 'off'} mode={appliance.mode} "
            f"humidity={appliance.current_humidity}% "
            f"target={appliance.target_humidity}% "
            f"tank={appliance.tank_level}%{' FULL' if appliance.tank_full else ''}",
        )
    except Exception as exc:  # noqa: BLE001
        say(step, False, error_text(exc))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--save-keys", metavar="PATH", help="write token and key here (mode 600)")
    parser.add_argument("--region", choices=sorted(REGIONS), help="probe one region only")
    args = parser.parse_args(argv)

    try:
        import midea_beautiful  # noqa: F401
    except ImportError:
        print("midea_beautiful is missing: pip install midea-beautiful-air", file=sys.stderr)
        return 2

    email, password = get_credentials()
    _SECRETS.extend([email, password])
    print("Read-only probe: nothing is changed on the device.\n")
    results = []
    for region in REGIONS:
        if args.region and region != args.region:
            continue
        results.append(probe_region(region, email, password, args.save_keys))
        print()
    print("\n".join(verdict(results)))
    return 0 if any(r.status or r.token for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
