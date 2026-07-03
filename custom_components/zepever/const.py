"""Constants for the Epever integration."""

DOMAIN = "zepever"

CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_ADDRESS = "device_address"
CONF_DEVICE_PORT = "device_port"
CONF_UNIT_ID = "unit_id"

DEFAULT_PORT = 9999
DEFAULT_UNIT_ID = 1
DEFAULT_SCAN_INTERVAL = 5  # seconds

# MPPT reacquire experiment (docs/epever_mppt_reacquire_experiment.md)
SERVICE_FORCE_MPPT_REACQUIRE = "force_mppt_reacquire"
ATTR_OFF_SECONDS = "off_seconds"
DEFAULT_OFF_SECONDS = 5
MIN_OFF_SECONDS = 2
MAX_OFF_SECONDS = 15
REACQUIRE_COOLDOWN_SECONDS = 60
