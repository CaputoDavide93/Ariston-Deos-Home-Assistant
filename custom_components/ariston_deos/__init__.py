"""Ariston Deos dehumidifier through the Ariston Clima cloud."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import AristonCloudAuthError, AristonCloudError, AristonDeosApi
from .const import (
    CONF_ACCOUNT,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import AristonDeosCoordinator

type AristonDeosConfigEntry = ConfigEntry[AristonDeosCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: AristonDeosConfigEntry) -> bool:
    """Log in once, then poll."""
    api = AristonDeosApi(
        entry.data[CONF_REGION], entry.data[CONF_ACCOUNT], entry.data[CONF_PASSWORD]
    )
    try:
        await hass.async_add_executor_job(api.login)
    except AristonCloudAuthError as err:
        raise ConfigEntryAuthFailed("Login was refused") from err
    except AristonCloudError as err:
        raise ConfigEntryNotReady(str(err)) from err

    interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = AristonDeosCoordinator(hass, entry, api, interval)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _reload(hass: HomeAssistant, entry: AristonDeosConfigEntry) -> None:
    """Apply a changed scan interval."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AristonDeosConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
