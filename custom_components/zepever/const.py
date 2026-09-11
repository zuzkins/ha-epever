"""Constants for the Epever integration."""

DOMAIN = "zepever"

CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_ADDRESS = "device_address"
CONF_DEVICE_PORT = "device_port"
CONF_UNIT_ID = "unit_id"

DEFAULT_PORT = 9999
DEFAULT_UNIT_ID = 1
DEFAULT_SCAN_INTERVAL = 5  # seconds

BATTERY_VOLTAGE_STATUS_LOW_VOLTAGE_DISCONNECT = "low_voltage_disconnect"
BATTERY_VOLTAGE_STATUSES = {
    0: "normal",
    1: "over_voltage",
    2: "under_voltage",
    3: BATTERY_VOLTAGE_STATUS_LOW_VOLTAGE_DISCONNECT,
    4: "fault",
}
BATTERY_VOLTAGE_STATUS_OPTIONS = (*BATTERY_VOLTAGE_STATUSES.values(), "unknown")

LOAD_CONTROL_MODE_MANUAL = 0
LOAD_CONTROL_MODES = {
    0: "Manual control",
    1: "Light on/off",
    2: "Light on + timer",
    3: "Time control",
}

# MPPT reacquire experiment (docs/epever_mppt_reacquire_experiment.md)
SERVICE_FORCE_MPPT_REACQUIRE = "force_mppt_reacquire"
ATTR_OFF_SECONDS = "off_seconds"
DEFAULT_OFF_SECONDS = 5
MIN_OFF_SECONDS = 2
MAX_OFF_SECONDS = 15
REACQUIRE_COOLDOWN_SECONDS = 60
