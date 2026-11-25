"""Sensor platform for Epever integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BATTERY_VOLTAGE_STATUS_OPTIONS,
    CHARGING_STATUS_OPTIONS,
    CONF_DEVICE_NAME,
    CONNECTION_QUALITY_OPTIONS,
    DEVICE_TYPE_HP,
    DOMAIN,
)
from .coordinator import EpeverDataUpdateCoordinator
from .hp_sensor import HP_SENSOR_DESCRIPTIONS, HpSensorEntityDescription

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="pv_voltage",
        name="PV Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="pv_current",
        name="PV Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="pv_power",
        name="PV Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="battery_voltage",
        name="Battery Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="battery_current",
        name="Battery Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="battery_power",
        name="Battery Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="load_voltage",
        name="Load Voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="load_current",
        name="Load Current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="load_power",
        name="Load Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="device_temperature",
        name="Device Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="internal_battery_temperature",
        name="Internal Battery Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="remote_battery_temperature",
        name="Remote Battery Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="battery_state_of_charge",
        name="Battery State of Charge",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="battery_voltage_status",
        translation_key="battery_voltage_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(BATTERY_VOLTAGE_STATUS_OPTIONS),
    ),
    SensorEntityDescription(
        key="charging_status",
        translation_key="charging_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(CHARGING_STATUS_OPTIONS),
    ),
    SensorEntityDescription(
        key="generated_energy_today",
        name="Generated Energy Today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="generated_energy_this_month",
        name="Generated Energy This Month",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="generated_energy_this_year",
        name="Generated Energy This Year",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="total_generated_energy",
        name="Total Generated Energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="consumed_energy_today",
        name="Consumed Energy Today",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="consumed_energy_this_month",
        name="Consumed Energy This Month",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="consumed_energy_this_year",
        name="Consumed Energy This Year",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="total_consumed_energy",
        name="Total Consumed Energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="battery_temperature",
        name="Battery Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="ambient_temperature",
        name="Ambient Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
)

# Reports on the link itself, so it is fed from coordinator poll statistics
# rather than device data.
CONNECTION_QUALITY_DESCRIPTION = SensorEntityDescription(
    key="connection_quality",
    translation_key="connection_quality",
    device_class=SensorDeviceClass.ENUM,
    options=list(CONNECTION_QUALITY_OPTIONS),
    entity_category=EntityCategory.DIAGNOSTIC,
)

# Its own sensor rather than an attribute: it changes only when a failure
# enters or leaves the window, and gets history and statistics this way.
POLL_FAILURE_RATE_DESCRIPTION = SensorEntityDescription(
    key="poll_failure_rate",
    translation_key="poll_failure_rate",
    native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT,
    suggested_display_precision=1,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Epever sensors from a config entry."""
    coordinator: EpeverDataUpdateCoordinator = entry.runtime_data

    sensors: list[EpeverSensor]
    if coordinator.device_type == DEVICE_TYPE_HP:
        sensors = [
            EpeverHpSensor(coordinator, description)
            for description in HP_SENSOR_DESCRIPTIONS
        ]
    else:
        sensors = [
            EpeverSensor(coordinator, description)
            for description in SENSOR_DESCRIPTIONS
        ]
    async_add_entities(
        [
            *sensors,
            EpeverConnectionQualitySensor(coordinator, CONNECTION_QUALITY_DESCRIPTION),
            EpeverPollFailureRateSensor(coordinator, POLL_FAILURE_RATE_DESCRIPTION),
        ]
    )


class EpeverSensor(CoordinatorEntity[EpeverDataUpdateCoordinator], SensorEntity):
    """Representation of an Epever sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EpeverDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        device_name = coordinator.config_entry.data.get(CONF_DEVICE_NAME, "Epever")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            name=device_name,
            manufacturer="Epever",
            model=coordinator.device_model,
        )

    @property
    def native_value(self) -> float | str | None:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.key)


class EpeverHpSensor(EpeverSensor):
    """Sensor decoded from a register of the HP inverter."""

    entity_description: HpSensorEntityDescription

    @property
    def native_value(self) -> float | None:
        """Return the scaled signed register value."""
        if self.coordinator.data is None:
            return None
        description = self.entity_description
        value = self.coordinator.data["registers"][description.address]
        if value > 0x7FFF:
            value -= 0x10000
        return value / description.divisor if description.divisor > 1 else value


class EpeverConnectionQualitySensor(EpeverSensor):
    """Link health derived from recent poll outcomes."""

    @property
    def available(self) -> bool:
        """Stay available: this sensor has to report the outage itself."""
        return True

    @property
    def native_value(self) -> str:
        """Return ok, degraded or offline."""
        return self.coordinator.connection_quality

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose failure details; these change only when a poll fails."""
        return {
            "consecutive_failures": self.coordinator.consecutive_failures,
            "last_failed_segment": self.coordinator.last_failed_segment,
        }


class EpeverPollFailureRateSensor(EpeverSensor):
    """Share of failed polls within the recent window."""

    @property
    def available(self) -> bool:
        """Stay available alongside the connection quality sensor."""
        return True

    @property
    def native_value(self) -> float:
        """Return the failure rate in percent."""
        return round(self.coordinator.recent_failure_rate * 100, 1)
