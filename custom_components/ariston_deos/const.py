"""Constants for Ariston Deos."""

from __future__ import annotations

DOMAIN = "ariston_deos"

CONF_REGION = "region"
CONF_ACCOUNT = "account"
CONF_PASSWORD = "password"
CONF_APPLIANCE_ID = "appliance_id"
CONF_SCAN_INTERVAL = "scan_interval"

REGION_EU = "eu"
REGION_US = "us"
REGIONS = [REGION_EU, REGION_US]

# 300 s by default: no quota is documented, and the state only changes when someone
# presses a button (a set command also refreshes at once).
DEFAULT_SCAN_INTERVAL = 300
MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 900

PLATFORMS = ["humidifier", "sensor", "binary_sensor"]
