"""Binary sensor platform for Epever integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_NAME, DOMAIN
from .coordinator import EpeverDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Epever binary sensors from a config entry."""
    coordinator: EpeverDataUpdateCoordinator = entry.runtime_data
    async_add_entities([EpeverLoadOutputBinarySensor(coordinator)])


class EpeverLoadOutputBinarySensor(
    CoordinatorEntity[EpeverDataUpdateCoordinator], BinarySensorEntity
):
    """Report whether the physical load output is running."""

    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_has_entity_name = True
    _attr_translation_key = "load_output"

    def __init__(self, coordinator: EpeverDataUpdateCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_load_output"
        device_name = coordinator.config_entry.data.get(CONF_DEVICE_NAME, "Epever")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=device_name,
            manufacturer="Epever",
            model="Solar Charge Controller",
        )

    @property
    def available(self) -> bool:
        """Return whether the load output status is available."""
        return super().available and "load_output_on" in self.coordinator.data

    @property
    def is_on(self) -> bool | None:
        """Return whether the physical load output is running."""
        return self.coordinator.data.get("load_output_on")
