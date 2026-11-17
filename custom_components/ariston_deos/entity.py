"""Shared entity base."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AristonDeosCoordinator


class AristonDeosEntity(CoordinatorEntity[AristonDeosCoordinator]):
    """All entities hang off one device called Ariston Deos."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: AristonDeosCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.appliance_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.appliance_id)},
            name="Ariston Deos",
            manufacturer="Ariston",
            model="Deos 16S NET",
        )
