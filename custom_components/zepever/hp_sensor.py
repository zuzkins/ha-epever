"""Sensors of the HP series hybrid inverter.

Registers are named after the HP-AH definitions in EPEVER's Solar Guardian
app. Values the app doesn't list, or whose unit or scale is in doubt, are debug
sensors with a question mark: diagnostic, keyed by address and without a state
class or device class, so they can't end up in long-term statistics or the
Energy dashboard. The app's energy counters are named energy sensors:
they matched the app on a device.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)

HP_DEBUG_KEY_PREFIX = "hp_debug_"


@dataclass(frozen=True, kw_only=True)
class HpSensorEntityDescription(SensorEntityDescription):
    """Describe how a sensor is decoded from the registers."""

    address: int
    divisor: int = 1
    signed: bool = False
    # 32-bit value, low word first.
    long: bool = False
    # Bit field: lowest bit, width, and what its values mean.
    shift: int = 0
    width: int = 16
    states: dict[int, str] | None = None
    # Read from the optional energy block instead of the live block.
    energy: bool = False

    def decode(self, data: dict[str, dict[int, int]]) -> float | str | None:
        """Return the value, or None when its registers were not read."""
        registers = data["energy" if self.energy else "registers"]
        value = registers.get(self.address)
        if value is None:
            return None
        if self.long:
            high = registers.get(self.address + 1)
            if high is None:
                return None
            return value + (high << 16)
        if self.states is not None:
            return self.states.get(
                value >> self.shift & ((1 << self.width) - 1), "unknown"
            )
        if self.signed and value > 0x7FFF:
            value -= 0x10000
        return value / self.divisor if self.divisor > 1 else value


_CLASSES: dict[str, SensorDeviceClass] = {
    UnitOfElectricPotential.VOLT: SensorDeviceClass.VOLTAGE,
    UnitOfElectricCurrent.AMPERE: SensorDeviceClass.CURRENT,
    UnitOfFrequency.HERTZ: SensorDeviceClass.FREQUENCY,
    UnitOfPower.WATT: SensorDeviceClass.POWER,
    UnitOfTemperature.CELSIUS: SensorDeviceClass.TEMPERATURE,
    PERCENTAGE: SensorDeviceClass.BATTERY,
}


def _measurement(
    key: str,
    name: str,
    address: int,
    unit: str,
    divisor: int = 1,
    signed: bool = False,
) -> HpSensorEntityDescription:
    """Describe a measurement."""
    return HpSensorEntityDescription(
        key=key,
        name=name,
        device_class=_CLASSES[unit],
        native_unit_of_measurement=unit,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0 if divisor == 1 else 1,
        address=address,
        divisor=divisor,
        signed=signed,
    )


def _status(
    key: str, name: str, address: int, shift: int, width: int, states: dict[int, str]
) -> HpSensorEntityDescription:
    """Describe a status decoded from a bit field."""
    return HpSensorEntityDescription(
        key=key,
        name=name,
        translation_key=key,
        device_class=SensorDeviceClass.ENUM,
        options=[*states.values(), "unknown"],
        address=address,
        shift=shift,
        width=width,
        states=states,
    )


def _energy(key: str, name: str, address: int) -> HpSensorEntityDescription:
    """Describe an energy counter in whole kWh, daily or lifetime."""
    return HpSensorEntityDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        address=address,
        energy=True,
        long=True,
    )


def _debug(
    address: int,
    name: str,
    unit: str,
    divisor: int = 1,
    signed: bool = False,
    energy: bool = False,
    long: bool = False,
) -> HpSensorEntityDescription:
    """Describe a debug sensor."""
    return HpSensorEntityDescription(
        key=f"{HP_DEBUG_KEY_PREFIX}{address:04x}",
        name=f"{name}? (0x{address:04X})",
        native_unit_of_measurement=unit,
        entity_category=EntityCategory.DIAGNOSTIC,
        address=address,
        divisor=divisor,
        signed=signed,
        energy=energy,
        long=long,
    )


_VOLT = UnitOfElectricPotential.VOLT
_AMPERE = UnitOfElectricCurrent.AMPERE
_HERTZ = UnitOfFrequency.HERTZ
_WATT = UnitOfPower.WATT
_CELSIUS = UnitOfTemperature.CELSIUS
_KWH = UnitOfEnergy.KILO_WATT_HOUR

HP_SENSOR_DESCRIPTIONS: tuple[HpSensorEntityDescription, ...] = (
    _measurement("grid_voltage", "Grid Voltage", 0x300F, _VOLT, 10),
    _measurement("grid_current", "Grid Current", 0x3010, _AMPERE, 10),
    _measurement("grid_frequency", "Grid Frequency", 0x3011, _HERTZ, 10),
    _measurement("load_voltage", "Load Voltage", 0x3013, _VOLT, 10),
    _measurement("load_current", "Load Current", 0x3016, _AMPERE, 10),
    _measurement("load_frequency", "Load Frequency", 0x3019, _HERTZ, 10),
    # The app's Utility Power and Load Power cards.
    _measurement("grid_power", "Grid Power", 0x3012, _WATT),
    _measurement("load_power", "Load Power", 0x301A, _WATT),
    _measurement("battery_voltage", "Battery Voltage", 0x3021, _VOLT, 10),
    # Negative while discharging.
    _measurement("battery_current", "Battery Current", 0x3022, _AMPERE, 10, True),
    _measurement(
        "battery_state_of_charge", "Battery State of Charge", 0x3023, PERCENTAGE
    ),
    _measurement("pv1_voltage", "PV1 Voltage", 0x3026, _VOLT, 10),
    _measurement("pv2_voltage", "PV2 Voltage", 0x3027, _VOLT, 10),
    _measurement("pv1_current", "PV1 Current", 0x3029, _AMPERE, 10),
    _measurement("pv2_current", "PV2 Current", 0x302A, _AMPERE, 10),
    _measurement("pv1_power", "PV1 Power", 0x302C, _WATT),
    _measurement("pv2_power", "PV2 Power", 0x302D, _WATT),
    _measurement("pv_temperature", "PV Temperature", 0x3031, _CELSIUS, 10, True),
    # Not the Tracer's order: 2 is equalize and 3 is boost here.
    _status(
        "charging_status",
        "Charging Status",
        0x3025,
        0,
        3,
        {0: "no_charging", 1: "float", 2: "equalize", 3: "boost"},
    ),
    _status(
        "operating_mode",
        "Operating Mode",
        0x3038,
        13,
        2,
        {1: "normal", 2: "bypass"},
    ),
    _status(
        "battery_flow",
        "Battery Flow",
        0x3038,
        11,
        2,
        {0: "idle", 1: "charging", 2: "discharging"},
    ),
    _status(
        "grid_status",
        "Grid Status",
        0x3038,
        3,
        2,
        {1: "normal", 2: "abnormal"},
    ),
    # Not in the app, and read above the Load Power card's value.
    _debug(0x301B, "Load power", _WATT, signed=True),
    _debug(0x3020, "DC bus voltage", _VOLT, 10),
    # Steady 25.0 in every dump, possibly without a probe.
    _debug(0x3024, "Battery power", _WATT, signed=True),
    _debug(0x3030, "Battery temperature", _CELSIUS, 10, True),
    _debug(0x3032, "Temperature 3", _CELSIUS, 10, True),
    _debug(0x3033, "Temperature 4", _CELSIUS, 10, True),
    HpSensorEntityDescription(
        key="pv_power",
        name="PV Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        address=0x1057,
        energy=True,
    ),
    # Whole kWh, unscaled as in the app, which they matched on a device.
    _energy("pv1_energy_today", "PV1 Energy Today", 0x1000),
    _energy("pv1_energy_total", "PV1 Energy Total", 0x1006),
    _energy("pv2_energy_today", "PV2 Energy Today", 0x1008),
    _energy("pv2_energy_total", "PV2 Energy Total", 0x100E),
    _energy("utility_charging_today", "Utility Charging Today", 0x101A),
    _energy("utility_charging_total", "Total Utility Charging", 0x1020),
    _energy("load_usage_today", "Load Usage Today", 0x102A),
    _energy("load_usage_total", "Total Load Usage", 0x1030),
    _energy("generation_today", "Generation Today", 0x1046),
    _energy("generation_total", "Total Generation", 0x104C),
    _energy("usage_today", "Usage Today", 0x104E),
    _energy("usage_total", "Total Usage", 0x1054),
)
