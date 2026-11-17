"""Tank full sensor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AristonDeosConfigEntry
from .coordinator import AristonDeosCoordinator
from .entity import AristonDeosEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: AristonDeosConfigEntry, add: AddEntitiesCallback
) -> None:
    add([AristonDeosTankFull(entry.runtime_data)])


class AristonDeosTankFull(AristonDeosEntity, BinarySensorEntity):
    _attr_translation_key = "tank_full"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: AristonDeosCoordinator) -> None:
        super().__init__(coordinator, "tank_full")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.tank_full
