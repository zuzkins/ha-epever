"""Device type selection, and that HP inverters are never written to."""

import pytest
from homeassistant.data_entry_flow import InvalidData
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zepever.diagnostics import async_get_config_entry_diagnostics

DOMAIN = "zepever"


def data_for(dongle, device_type=None):
    """Build config entry data."""
    data = {
        "device_name": "Dev",
        "device_address": "127.0.0.1",
        "device_port": dongle.port,
    }
    return data | ({"device_type": device_type} if device_type else {})


async def setup(hass, dongle, device_type=None):
    """Set up an entry."""
    entry = MockConfigEntry(domain=DOMAIN, data=data_for(dongle, device_type))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def entities(hass, entry):
    """Return the registry entries of a config entry."""
    return er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)


def state(hass, entry, key):
    """Return the state of the entity with the given key."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{entry.entry_id}_{key}"
    )
    return hass.states.get(entity_id)


async def test_hp_sensors(hass, hp_dongle):
    """The dump decodes to the expected values, without statistics."""
    entry = await setup(hass, hp_dongle, "hp_inverter")
    assert {e.domain for e in entities(hass, entry)} == {"sensor"}
    expected = {
        0x300F: 233.8,
        0x3011: 49.9,
        0x301A: 818,
        0x301B: 757,
        0x3021: 50.4,
        0x3022: -0.4,
        0x3023: 96,
        0x3024: -20,
    }
    for address, value in expected.items():
        sensor = state(hass, entry, f"hp_debug_{address:04x}")
        assert float(sensor.state) == value
        assert "state_class" not in sensor.attributes
        assert "device_class" not in sensor.attributes
    assert all(f == 4 and c <= 16 for f, _, c in hp_dongle.requests)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_hp_rejects_writes(hass, hp_dongle):
    """Neither the service nor the coordinator writes to an HP inverter."""
    entry = await setup(hass, hp_dongle, "hp_inverter")
    device = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)[0]
    before = len(hp_dongle.requests)
    for data in ({}, {"device_id": device.id}):
        with pytest.raises(ServiceValidationError, match="Not supported"):
            await hass.services.async_call(
                DOMAIN, "force_mppt_reacquire", data, blocking=True
            )
    with pytest.raises(ServiceValidationError):
        await entry.runtime_data.async_set_load_control_mode(0)
    with pytest.raises(ServiceValidationError):
        await entry.runtime_data.async_set_manual_load_output(True)
    assert len(hp_dongle.requests) == before


async def test_hp_diagnostics(hass, hp_dongle):
    """Diagnostics carry the log, spaced by interval, without the address."""
    entry = await setup(hass, hp_dongle, "hp_inverter")
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    assert len(coordinator.register_log) == 1
    coordinator._last_register_log -= 300
    await coordinator.async_refresh()
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert len(result["register_log"]) == 2
    assert len(result["registers"]) == 200
    assert result["registers"]["0x3021"] == 504
    assert "127.0.0.1" not in str(result)


async def test_legacy_entry_is_tracer(hass, tracer_dongle):
    """An entry without a device type keeps everything a Tracer has."""
    entry = await setup(hass, tracer_dongle)
    assert {e.domain for e in entities(hass, entry)} == {
        "binary_sensor",
        "button",
        "select",
        "sensor",
        "switch",
    }
    assert not any("hp_debug" in e.unique_id for e in entities(hass, entry))
    assert entry.runtime_data.update_interval.total_seconds() == 5
    assert float(state(hass, entry, "battery_state_of_charge").state) == 80
    assert "data" in await async_get_config_entry_diagnostics(hass, entry)


async def test_service_still_finds_the_only_tracer(hass, hp_dongle, tracer_dongle):
    """Adding an HP inverter does not make the only Tracer ambiguous."""
    await setup(hass, hp_dongle, "hp_inverter")
    tracer = await setup(hass, tracer_dongle)
    calls = []

    async def reacquire(off_seconds):
        calls.append(off_seconds)

    tracer.runtime_data.async_force_mppt_reacquire = reacquire
    await hass.services.async_call(DOMAIN, "force_mppt_reacquire", {}, blocking=True)
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("fixture", "device_type", "works"),
    [
        ("hp_dongle", "hp_inverter", True),
        ("tracer_dongle", "tracer", True),
        ("hp_dongle", "tracer", False),
        ("tracer_dongle", "hp_inverter", False),
    ],
)
async def test_config_flow(hass, request, fixture, device_type, works):
    """The chosen type is validated against the device and stored."""
    dongle = request.getfixturevalue(fixture)
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], data_for(dongle, device_type)
    )
    await hass.async_block_till_done()
    if works:
        assert result["data"]["device_type"] == device_type
    else:
        assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_requires_a_choice(hass, tracer_dongle):
    """There is no default device type."""
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with pytest.raises(InvalidData, match="device_type"):
        await hass.config_entries.flow.async_configure(
            flow["flow_id"], data_for(tracer_dongle)
        )
