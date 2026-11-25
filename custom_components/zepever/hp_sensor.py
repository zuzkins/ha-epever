"""Sensors of the HP series hybrid inverter.

Registers are named after the HP-AH definitions in EPEVER's Solar Guardian
app. Values the app doesn't list, or whose unit or scale is in doubt, are debug
sensors with a question mark: diagnostic, keyed by address and without a state
class or device class, so they can't end up in long-term statistics or the
Energy dashboard.
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
    UnitOfApparentPower,
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
_VA = UnitOfApparentPower.VOLT_AMPERE
_CELSIUS = UnitOfTemperature.CELSIUS
_KWH = UnitOfEnergy.KILO_WATT_HOUR

HP_SENSOR_DESCRIPTIONS: tuple[HpSensorEntityDescription, ...] = (
    _measurement("grid_voltage", "Grid Voltage", 0x300F, _VOLT, 10),
    _measurement("grid_current", "Grid Current", 0x3010, _AMPERE, 10),
    _measurement("grid_frequency", "Grid Frequency", 0x3011, _HERTZ, 10),
    _measurement("load_voltage", "Load Voltage", 0x3013, _VOLT, 10),
    _measurement("load_current", "Load Current", 0x3016, _AMPERE, 10),
    _measurement("load_frequency", "Load Frequency", 0x3019, _HERTZ, 10),
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
    # The app says W, but the value equals V x A.
    _debug(0x3012, "Grid power", _VA),
    _debug(0x301A, "Load apparent power", _VA),
    _debug(0x301B, "Load power", _WATT, signed=True),
    _debug(0x3020, "DC bus voltage", _VOLT, 10),
    _debug(0x3024, "Battery power", _WATT, signed=True),
    # Steady 25.0 in every dump, possibly without a probe.
    _debug(0x3030, "Battery temperature", _CELSIUS, 10, True),
    _debug(0x3032, "Temperature 3", _CELSIUS, 10, True),
    _debug(0x3033, "Temperature 4", _CELSIUS, 10, True),
    # The app applies no scale to the counters; whole kWh looks coarse.
    _debug(0x1057, "Total PV power", _WATT, energy=True),
    _debug(0x1000, "PV1 energy today", _KWH, energy=True, long=True),
    _debug(0x1006, "PV1 energy total", _KWH, energy=True, long=True),
    _debug(0x1008, "PV2 energy today", _KWH, energy=True, long=True),
    _debug(0x100E, "PV2 energy total", _KWH, energy=True, long=True),
    _debug(0x101A, "Utility charging today", _KWH, energy=True, long=True),
    _debug(0x1020, "Utility charging total", _KWH, energy=True, long=True),
    _debug(0x102A, "Load energy today", _KWH, energy=True, long=True),
    _debug(0x1030, "Load energy total", _KWH, energy=True, long=True),
    _debug(0x1046, "Generation today", _KWH, energy=True, long=True),
    _debug(0x104C, "Generation total", _KWH, energy=True, long=True),
    _debug(0x104E, "Usage today", _KWH, energy=True, long=True),
    _debug(0x1054, "Usage total", _KWH, energy=True, long=True),
)
