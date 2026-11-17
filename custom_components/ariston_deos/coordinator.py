"""Polling coordinator for Ariston Deos."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AristonCloudAuthError, AristonCloudError, AristonDeosApi, DeosState
from .const import CONF_APPLIANCE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AristonDeosCoordinator(DataUpdateCoordinator[DeosState]):
    """Fetch the dehumidifier state through the cloud."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: AristonDeosApi,
        interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self.appliance_id: str = entry.data[CONF_APPLIANCE_ID]

    async def _async_update_data(self) -> DeosState:
        try:
            return await self.hass.async_add_executor_job(
                self.api.query_state, self.appliance_id
            )
        except AristonCloudAuthError as err:
            raise ConfigEntryAuthFailed("Login was refused") from err
        except AristonCloudError as err:
            raise UpdateFailed(str(err)) from err

    async def async_set(self, **changes) -> None:
        """Send a change, show it at once, then confirm with a refresh."""
        try:
            state = await self.hass.async_add_executor_job(
                lambda: self.api.set(self.appliance_id, **changes)
            )
        except AristonCloudAuthError as err:
            # A service call is not a poll: ConfigEntryAuthFailed would not
            # start reauth from here, so start it ourselves.
            self.last_update_success = False
            self.async_update_listeners()
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError("Ariston login was refused, sign in again") from err
        except AristonCloudError as err:
            raise HomeAssistantError(f"Ariston change failed: {err}") from err
        self.async_set_updated_data(state)
        await self.async_request_refresh()
