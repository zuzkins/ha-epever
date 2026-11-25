"""Constants for the Epever integration."""

DOMAIN = "zepever"

CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_ADDRESS = "device_address"
CONF_DEVICE_PORT = "device_port"
CONF_UNIT_ID = "unit_id"
CONF_DEVICE_TYPE = "device_type"

# Entries created before the device type existed are all Tracers.
DEVICE_TYPE_TRACER = "tracer"
DEVICE_TYPE_HP = "hp_inverter"
DEVICE_TYPES = {
    DEVICE_TYPE_TRACER: "Solar charge controller (Tracer)",
    DEVICE_TYPE_HP: "HP series hybrid inverter (experimental, read-only)",
}
DEVICE_MODELS = {
    DEVICE_TYPE_TRACER: "Solar Charge Controller",
    DEVICE_TYPE_HP: "HP Hybrid Inverter (experimental)",
}

DEFAULT_PORT = 9999
DEFAULT_UNIT_ID = 1
DEFAULT_SCAN_INTERVAL = 5  # seconds
HP_SCAN_INTERVAL = 30  # seconds
# Consecutive failed polls before entities go unavailable; earlier failures
# keep serving the last good data so a dropped frame doesn't flap them.
MAX_CONSECUTIVE_FAILURES = 3

# Connection quality sensor: failure rate over the last N polls above which
# the link counts as degraded even while polls currently succeed. Set to
# 2 of 12 so a lone dropped frame (routine over WiFi + VPN) stays green.
CONNECTION_QUALITY_WINDOW = 12  # polls, ~1 min at the default interval
CONNECTION_QUALITY_DEGRADED_RATE = 0.15
CONNECTION_QUALITY_OK = "ok"
CONNECTION_QUALITY_DEGRADED = "degraded"
CONNECTION_QUALITY_OFFLINE = "offline"
CONNECTION_QUALITY_OPTIONS = (
    CONNECTION_QUALITY_OK,
    CONNECTION_QUALITY_DEGRADED,
    CONNECTION_QUALITY_OFFLINE,
)

BATTERY_VOLTAGE_STATUS_LOW_VOLTAGE_DISCONNECT = "low_voltage_disconnect"
BATTERY_VOLTAGE_STATUSES = {
    0: "normal",
    1: "over_voltage",
    2: "under_voltage",
    3: BATTERY_VOLTAGE_STATUS_LOW_VOLTAGE_DISCONNECT,
    4: "fault",
}
BATTERY_VOLTAGE_STATUS_OPTIONS = (*BATTERY_VOLTAGE_STATUSES.values(), "unknown")

# Charging equipment status register 0x3201, bits D3-D2.
CHARGING_STATUSES = {
    0: "no_charging",
    1: "float",
    2: "boost",
    3: "equalize",
}
CHARGING_STATUS_OPTIONS = (*CHARGING_STATUSES.values(), "unknown")

LOAD_CONTROL_MODE_MANUAL = 0
LOAD_CONTROL_MODES = {
    0: "Manual control",
    1: "Light on/off",
    2: "Light on + timer",
    3: "Time control",
}

# Raw register log of the HP inverter, for the diagnostics download.
HP_LOG_INTERVAL = 300  # seconds
# Energy blocks may go unanswered, which costs seconds per attempt.
HP_ENERGY_INTERVAL = 300  # seconds
HP_ENERGY_RETRY_INTERVAL = 3600  # seconds, until a block has answered once
HP_LOG_SIZE = 288  # snapshots, 24 h

# MPPT reacquire experiment (docs/epever_mppt_reacquire_experiment.md)
SERVICE_FORCE_MPPT_REACQUIRE = "force_mppt_reacquire"
ATTR_OFF_SECONDS = "off_seconds"
DEFAULT_OFF_SECONDS = 5
MIN_OFF_SECONDS = 2
MAX_OFF_SECONDS = 15
REACQUIRE_COOLDOWN_SECONDS = 60
