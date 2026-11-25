"""Diagnostics download for the Epever integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_ADDRESS, CONF_DEVICE_NAME, DEVICE_TYPE_HP
from .coordinator import EpeverDataUpdateCoordinator

TO_REDACT = {CONF_DEVICE_ADDRESS, CONF_DEVICE_NAME}


def _dump(registers: dict[int, int]) -> dict[str, int]:
    """Make a register snapshot readable and JSON friendly."""
    return {f"0x{address:04X}": value for address, value in registers.items()}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return the latest data and, for HP inverters, the register log."""
    coordinator: EpeverDataUpdateCoordinator = entry.runtime_data
    result: dict[str, Any] = {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "connection_quality": coordinator.connection_quality,
        "recent_failure_rate": coordinator.recent_failure_rate,
        "last_failed_segment": coordinator.last_failed_segment,
    }
    data = coordinator.data or {}
    if coordinator.device_type == DEVICE_TYPE_HP:
        result["registers"] = _dump(
            {**data.get("energy", {}), **data.get("registers", {})}
        )
        result["energy_errors"] = {
            f"0x{address:04X}": error
            for address, error in coordinator.energy_errors.items()
        }
        result["register_log"] = [
            {"time": when, "registers": _dump(registers)}
            for when, registers in coordinator.register_log
        ]
    else:
        result["data"] = data
    return result
