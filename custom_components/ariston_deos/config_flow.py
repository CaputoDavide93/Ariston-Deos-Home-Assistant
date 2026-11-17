"""Config, reauth and options flows."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .api import AristonCloudAuthError, AristonCloudError, AristonDeosApi, DeosDevice
from .const import (
    CONF_ACCOUNT,
    CONF_APPLIANCE_ID,
    CONF_PASSWORD,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    REGION_EU,
    REGIONS,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default=REGION_EU): SelectSelector(
            SelectSelectorConfig(options=REGIONS, translation_key="region")
        ),
        vol.Required(CONF_ACCOUNT): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class AristonDeosConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._creds: dict[str, str] = {}
        self._devices: list[DeosDevice] = []

    async def _login(self, creds: dict[str, str]) -> tuple[list[DeosDevice], str | None]:
        api = AristonDeosApi(
            creds[CONF_REGION], creds[CONF_ACCOUNT], creds[CONF_PASSWORD]
        )
        try:
            await self.hass.async_add_executor_job(api.login)
            devices = await self.hass.async_add_executor_job(api.list_dehumidifiers)
        except AristonCloudAuthError:
            return [], "invalid_auth"
        except AristonCloudError:
            return [], "cannot_connect"
        return devices, (None if devices else "no_devices")

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            devices, error = await self._login(user_input)
            if error is None:
                self._creds = dict(user_input)
                self._devices = devices
                if len(devices) == 1:
                    return await self._create(devices[0])
                return await self.async_step_device()
            errors["base"] = error
        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            chosen = next(
                d for d in self._devices if d.appliance_id == user_input[CONF_APPLIANCE_ID]
            )
            return await self._create(chosen)
        options = [
            SelectOptionDict(value=d.appliance_id, label=d.name) for d in self._devices
        ]
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {vol.Required(CONF_APPLIANCE_ID): SelectSelector(SelectSelectorConfig(options=options))}
            ),
        )

    async def _create(self, device: DeosDevice) -> ConfigFlowResult:
        await self.async_set_unique_id(device.appliance_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Ariston Deos",
            data={**self._creds, CONF_APPLIANCE_ID: device.appliance_id},
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            creds = {
                CONF_REGION: entry.data[CONF_REGION],
                CONF_ACCOUNT: entry.data[CONF_ACCOUNT],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            _, error = await self._login(creds)
            if error in (None, "no_devices"):
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return AristonDeosOptionsFlow()


class AristonDeosOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                    )
                }
            ),
        )
