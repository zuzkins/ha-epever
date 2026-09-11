"""Switch platform for Epever integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_NAME, DOMAIN, LOAD_CONTROL_MODE_MANUAL
from .coordinator import EpeverDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Epever switches from a config entry."""
    coordinator: EpeverDataUpdateCoordinator = entry.runtime_data
    async_add_entities([EpeverManualLoadSwitch(coordinator)])


class EpeverManualLoadSwitch(
    CoordinatorEntity[EpeverDataUpdateCoordinator], SwitchEntity
):
    """Control the load output while the controller is in manual mode."""

    _attr_has_entity_name = True
    _attr_name = "Manual load"

    def __init__(self, coordinator: EpeverDataUpdateCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_manual_load"
        device_name = coordinator.config_entry.data.get(CONF_DEVICE_NAME, "Epever")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=device_name,
            manufacturer="Epever",
            model="Solar Charge Controller",
        )

    @property
    def available(self) -> bool:
        """Return whether manual load control is available."""
        return (
            super().available
            and self.coordinator.data.get("load_control_mode")
            == LOAD_CONTROL_MODE_MANUAL
            and "load_output_on" in self.coordinator.data
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether the physical load output is active."""
        return self.coordinator.data.get("load_output_on")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the manual load output."""
        await self.coordinator.async_set_manual_load_output(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the manual load output."""
        await self.coordinator.async_set_manual_load_output(False)
