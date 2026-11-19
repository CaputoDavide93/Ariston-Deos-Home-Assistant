"""One-button presets, so anyone in the house can use the dehumidifier."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AristonDeosConfigEntry
from .api import PRESETS
from .coordinator import AristonDeosCoordinator
from .entity import AristonDeosEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: AristonDeosConfigEntry, add: AddEntitiesCallback
) -> None:
    add([AristonDeosPreset(entry.runtime_data, key) for key in PRESETS])


class AristonDeosPreset(AristonDeosEntity, ButtonEntity):
    """Pressing it sends that preset's power and mode in one command."""

    def __init__(self, coordinator: AristonDeosCoordinator, key: str) -> None:
        super().__init__(coordinator, f"preset_{key}")
        self._key = key
        self._attr_translation_key = f"preset_{key}"

    async def async_press(self) -> None:
        await self.coordinator.async_set(**PRESETS[self._key])
