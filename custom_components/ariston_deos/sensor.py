"""Current humidity sensor."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AristonDeosConfigEntry
from .coordinator import AristonDeosCoordinator
from .entity import AristonDeosEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: AristonDeosConfigEntry, add: AddEntitiesCallback
) -> None:
    add([AristonDeosHumiditySensor(entry.runtime_data)])


class AristonDeosHumiditySensor(AristonDeosEntity, SensorEntity):
    _attr_translation_key = "current_humidity"
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: AristonDeosCoordinator) -> None:
        super().__init__(coordinator, "current_humidity")

    @property
    def native_value(self) -> int:
        return self.coordinator.data.current_humidity
