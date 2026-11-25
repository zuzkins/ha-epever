"""Binary sensor platform for Epever integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_NAME, DEVICE_TYPE_HP, DOMAIN
from .coordinator import EpeverDataUpdateCoordinator
from .hp_com import HP_FAULTS, HP_NOTICES, active_bits


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Epever binary sensors from a config entry."""
    coordinator: EpeverDataUpdateCoordinator = entry.runtime_data
    if coordinator.device_type == DEVICE_TYPE_HP:
        async_add_entities([EpeverHpFaultBinarySensor(coordinator)])
        return
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


class EpeverHpFaultBinarySensor(
    CoordinatorEntity[EpeverDataUpdateCoordinator], BinarySensorEntity
):
    """Report whether the HP inverter signals any fault."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True
    _attr_name = "Fault"

    def __init__(self, coordinator: EpeverDataUpdateCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_fault"
        device_name = coordinator.config_entry.data.get(CONF_DEVICE_NAME, "Epever")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=device_name,
            manufacturer="Epever",
            model=coordinator.device_model,
        )

    @property
    def is_on(self) -> bool:
        """Return whether any fault bit is set."""
        return bool(active_bits(self.coordinator.data["registers"], HP_FAULTS))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """List the active faults and notices."""
        registers = self.coordinator.data["registers"]
        return {
            "faults": active_bits(registers, HP_FAULTS),
            "notices": active_bits(registers, HP_NOTICES),
        }
