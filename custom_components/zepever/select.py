"""Select platform for Epever integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_NAME, DOMAIN, LOAD_CONTROL_MODES
from .coordinator import EpeverDataUpdateCoordinator

LOAD_CONTROL_MODE_VALUES = {name: value for value, name in LOAD_CONTROL_MODES.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Epever selects from a config entry."""
    coordinator: EpeverDataUpdateCoordinator = entry.runtime_data
    async_add_entities([EpeverLoadControlModeSelect(coordinator)])


class EpeverLoadControlModeSelect(
    CoordinatorEntity[EpeverDataUpdateCoordinator], SelectEntity
):
    """Select the controller's load-output control mode."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_has_entity_name = True
    _attr_name = "Load control mode"

    def __init__(self, coordinator: EpeverDataUpdateCoordinator) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        self._attr_options = list(LOAD_CONTROL_MODE_VALUES)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_load_control_mode"
        device_name = coordinator.config_entry.data.get(CONF_DEVICE_NAME, "Epever")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=device_name,
            manufacturer="Epever",
            model="Solar Charge Controller",
        )

    @property
    def available(self) -> bool:
        """Return whether the controller reported a supported mode."""
        return (
            super().available
            and self.coordinator.data.get("load_control_mode") in LOAD_CONTROL_MODES
        )

    @property
    def current_option(self) -> str | None:
        """Return the current load-control mode."""
        return LOAD_CONTROL_MODES.get(self.coordinator.data.get("load_control_mode"))

    async def async_select_option(self, option: str) -> None:
        """Set the load-control mode."""
        await self.coordinator.async_set_load_control_mode(
            LOAD_CONTROL_MODE_VALUES[option]
        )
