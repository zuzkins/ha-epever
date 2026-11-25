"""Candidate sensors of the HP series hybrid inverter.

The meanings are guesses from register dumps, hence the question marks. They
deliberately carry no state class or device class, so a wrong guess can't end
up in long-term statistics or the Energy dashboard. Keys are the addresses:
confirmed sensors get new, permanent keys.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)


@dataclass(frozen=True, kw_only=True)
class HpSensorEntityDescription(SensorEntityDescription):
    """Describe a sensor decoded from a single signed register."""

    address: int
    divisor: int = 1


def _candidate(
    address: int, name: str, unit: str, divisor: int = 1
) -> HpSensorEntityDescription:
    """Build the description of a candidate sensor."""
    return HpSensorEntityDescription(
        key=f"hp_debug_{address:04x}",
        name=f"{name}? (0x{address:04X})",
        native_unit_of_measurement=unit,
        entity_category=EntityCategory.DIAGNOSTIC,
        address=address,
        divisor=divisor,
    )


HP_SENSOR_DESCRIPTIONS: tuple[HpSensorEntityDescription, ...] = (
    _candidate(0x300F, "Grid voltage", UnitOfElectricPotential.VOLT, 10),
    _candidate(0x3010, "Grid current", UnitOfElectricCurrent.AMPERE, 10),
    _candidate(0x3011, "Grid frequency", UnitOfFrequency.HERTZ, 10),
    _candidate(0x3012, "Grid power", UnitOfApparentPower.VOLT_AMPERE),
    _candidate(0x3013, "Output voltage", UnitOfElectricPotential.VOLT, 10),
    _candidate(0x3016, "Output current", UnitOfElectricCurrent.AMPERE, 10),
    _candidate(0x3019, "Output frequency", UnitOfFrequency.HERTZ, 10),
    _candidate(0x301A, "Output apparent power", UnitOfApparentPower.VOLT_AMPERE),
    _candidate(0x301B, "Output power", UnitOfPower.WATT),
    _candidate(0x3020, "DC bus voltage", UnitOfElectricPotential.VOLT, 10),
    _candidate(0x3021, "Battery voltage", UnitOfElectricPotential.VOLT, 10),
    _candidate(0x3022, "Battery current", UnitOfElectricCurrent.AMPERE, 10),
    _candidate(0x3023, "Battery state of charge", PERCENTAGE),
    _candidate(0x3024, "Battery power", UnitOfPower.WATT),
    _candidate(0x3030, "Temperature 1", UnitOfTemperature.CELSIUS, 10),
    _candidate(0x3031, "Temperature 2", UnitOfTemperature.CELSIUS, 10),
    _candidate(0x3032, "Temperature 3", UnitOfTemperature.CELSIUS, 10),
    _candidate(0x3033, "Temperature 4", UnitOfTemperature.CELSIUS, 10),
)
