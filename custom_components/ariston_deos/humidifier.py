"""Dehumidifier entity."""

from __future__ import annotations

from typing import Any

from homeassistant.components.humidifier import (
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AristonDeosConfigEntry
from .api import HUMIDITY_STEP, MAX_HUMIDITY, MIN_HUMIDITY, MODES
from .coordinator import AristonDeosCoordinator
from .entity import AristonDeosEntity

_MODE_TO_NUM = {name: num for num, name in MODES.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: AristonDeosConfigEntry, add: AddEntitiesCallback
) -> None:
    add([AristonDeosHumidifier(entry.runtime_data)])


class AristonDeosHumidifier(AristonDeosEntity, HumidifierEntity):
    """The dehumidifier itself."""

    _attr_name = None
    _attr_device_class = HumidifierDeviceClass.DEHUMIDIFIER
    _attr_supported_features = HumidifierEntityFeature.MODES
    _attr_min_humidity = MIN_HUMIDITY
    _attr_max_humidity = MAX_HUMIDITY
    _attr_target_humidity_step = HUMIDITY_STEP
    _attr_available_modes = list(MODES.values())
    _attr_translation_key = "dehumidifier"

    def __init__(self, coordinator: AristonDeosCoordinator) -> None:
        super().__init__(coordinator, "humidifier")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.power

    @property
    def target_humidity(self) -> int:
        return self.coordinator.data.target_humidity

    @property
    def mode(self) -> str | None:
        return MODES.get(self.coordinator.data.mode)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set(power=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set(power=False)

    async def async_set_humidity(self, humidity: int) -> None:
        # Snap to the device step so the cloud never sees an odd value.
        snapped = round(humidity / HUMIDITY_STEP) * HUMIDITY_STEP
        snapped = max(MIN_HUMIDITY, min(MAX_HUMIDITY, snapped))
        await self.coordinator.async_set(target_humidity=snapped)

    async def async_set_mode(self, mode: str) -> None:
        await self.coordinator.async_set(mode=_MODE_TO_NUM[mode])
