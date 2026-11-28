"""Device type selection, and that HP inverters are never written to."""

import time

import pytest
from homeassistant.data_entry_flow import InvalidData
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.zepever.diagnostics import async_get_config_entry_diagnostics

DOMAIN = "zepever"
ENERGY_TOTALS = (
    "pv1_energy_total",
    "pv2_energy_total",
    "utility_charging_total",
    "load_usage_total",
    "generation_total",
    "usage_total",
)
ENERGY_TODAY = (
    "pv1_energy_today",
    "pv2_energy_today",
    "utility_charging_today",
    "load_usage_today",
    "generation_today",
    "usage_today",
)


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


async def test_hp_night_dump(hass, hp_dongle):
    """The dump decodes to the expected values, without Energy statistics."""
    entry = await setup(hass, hp_dongle, "hp_inverter")
    assert {e.domain for e in entities(hass, entry)} == {"sensor", "binary_sensor"}
    expected = {
        "grid_voltage": 233.8,
        "grid_frequency": 49.9,
        "load_voltage": 233.5,
        "battery_voltage": 50.4,
        "battery_current": -0.4,
        "battery_state_of_charge": 96,
        "pv1_voltage": 0,
        "pv_temperature": 23.4,
        "grid_power": 817,
        "load_power": 818,
        "hp_debug_301b": 757,
        "battery_power": -20,
    }
    for key, value in expected.items():
        assert float(state(hass, entry, key).state) == value
    assert state(hass, entry, "charging_status").state == "no_charging"
    assert state(hass, entry, "operating_mode").state == "bypass"
    assert state(hass, entry, "battery_flow").state == "discharging"
    assert state(hass, entry, "grid_status").state == "normal"
    fault = hass.states.get("binary_sensor.dev_fault")
    assert fault.state == "off"
    assert fault.attributes["faults"] == fault.attributes["notices"] == []
    for entity in entities(hass, entry):
        attributes = hass.states.get(entity.entity_id).attributes
        if attributes.get("device_class") == "energy":
            assert entity.unique_id.endswith(ENERGY_TOTALS + ENERGY_TODAY)
        if "hp_debug" in entity.unique_id:
            assert "state_class" not in attributes
            assert "device_class" not in attributes
    assert all(f == 4 and c <= 16 for f, _, c in hp_dongle.requests)
    # An unanswered energy block must not slow down the setup.
    assert all(a >= 0x3000 for _, a, _ in hp_dongle.requests)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_hp_day_and_faults(hass, hp_dongle):
    """PV, equalize/boost and fault bits decode."""
    hp_dongle.registers |= {
        0x3025: 3,
        0x3026: 3105,
        0x3029: 42,
        0x302C: 1304,
        0x3022: 250,
        0x3038: (1 << 13) | (1 << 11) | (2 << 3),
        0x3006: 1 << 10,
        0x3008: 1 << 9,
    }
    entry = await setup(hass, hp_dongle, "hp_inverter")
    assert float(state(hass, entry, "pv1_voltage").state) == 310.5
    assert float(state(hass, entry, "pv1_current").state) == 4.2
    assert float(state(hass, entry, "pv1_power").state) == 1304
    assert float(state(hass, entry, "battery_current").state) == 25
    assert state(hass, entry, "charging_status").state == "boost"
    assert state(hass, entry, "operating_mode").state == "normal"
    assert state(hass, entry, "battery_flow").state == "charging"
    assert state(hass, entry, "grid_status").state == "abnormal"
    fault = hass.states.get("binary_sensor.dev_fault")
    assert fault.state == "on"
    assert fault.attributes["faults"] == ["Inverter over temperature"]
    assert fault.attributes["notices"] == ["Remote temperature sensor not connected"]
    hp_dongle.registers[0x3006] = 0
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.dev_fault").state == "off"


def energy_requests(dongle):
    """Return the addresses of the energy reads so far."""
    return [address for _, address, _ in dongle.requests if address < 0x3000]


async def test_hp_energy(hass, hp_dongle):
    """One energy block is read per poll, then all wait for their interval."""
    hp_dongle.registers |= {a: 0 for a in range(0x1000, 0x1058)}
    hp_dongle.registers |= {0x1000: 7, 0x104C: 1, 0x104D: 2}
    entry = await setup(hass, hp_dongle, "hp_inverter")
    assert state(hass, entry, "pv1_energy_today").state == "unknown"
    coordinator = entry.runtime_data
    for _ in range(7):
        await coordinator.async_refresh()
    await hass.async_block_till_done()
    requests = energy_requests(hp_dongle)
    assert [a for a in requests if a != 0x1056] == [0x1000, 0x1018, 0x102A, 0x1046]
    # Total PV power is read on every poll but the first.
    assert requests.count(0x1056) == 7
    assert float(state(hass, entry, "pv1_energy_today").state) == 7
    total = state(hass, entry, "generation_total")
    assert float(total.state) == 0x20001
    assert total.attributes["device_class"] == "energy"
    assert total.attributes["state_class"] == "total_increasing"
    assert total.attributes["unit_of_measurement"] == "kWh"
    for key in ENERGY_TOTALS + ENERGY_TODAY:
        assert state(hass, entry, key).attributes["state_class"] == "total_increasing"
    assert float(state(hass, entry, "usage_total").state) == 0
    assert coordinator.energy_errors == {}
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert "0x1000" in result["registers"]


async def test_hp_pv_power(hass, hp_dongle):
    """Total PV power follows every poll and is never shown stale."""
    hp_dongle.registers |= {0x1056: 0, 0x1057: 529}
    entry = await setup(hass, hp_dongle, "hp_inverter")
    coordinator = entry.runtime_data
    assert state(hass, entry, "pv_power").state == "unknown"
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    pv_power = state(hass, entry, "pv_power")
    assert float(pv_power.state) == 529
    assert pv_power.attributes["device_class"] == "power"
    hp_dongle.registers[0x1057] = 700
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert float(state(hass, entry, "pv_power").state) == 700

    # Unanswered: unknown, live data unaffected, and retried after a while.
    del hp_dongle.registers[0x1056], hp_dongle.registers[0x1057]
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.last_update_success
    assert state(hass, entry, "pv_power").state == "unknown"
    assert float(state(hass, entry, "battery_voltage").state) == 50.4
    assert 0x1056 in coordinator.energy_errors
    due = coordinator._energy_due[(0x1056, 2)] - time.monotonic()
    assert 290 < due < 301


async def test_hp_silent_energy_block(hass, hp_dongle):
    """A silent energy block hides neither later blocks nor live data."""
    hp_dongle.registers |= {a: 3 for a in range(0x102A, 0x1032)}
    entry = await setup(hass, hp_dongle, "hp_inverter")
    coordinator = entry.runtime_data
    for _ in range(5):
        await coordinator.async_refresh()
        assert coordinator.last_update_success
        assert coordinator.consecutive_failures == 0
    await hass.async_block_till_done()
    assert float(state(hass, entry, "load_usage_today").state) == 0x30003
    assert state(hass, entry, "pv1_energy_today").state == "unknown"
    assert float(state(hass, entry, "battery_voltage").state) == 50.4
    assert set(coordinator.energy_errors) == {0x1000, 0x1018, 0x1046, 0x1056}

    # Silent blocks back off for longer than the answering one.
    now = time.monotonic()
    due = {block[0]: at - now for block, at in coordinator._energy_due.items()}
    assert due[0x102A] < 301
    assert all(due[a] > 3000 for a in coordinator.energy_errors)
    count = len(energy_requests(hp_dongle))
    await coordinator.async_refresh()
    assert len(energy_requests(hp_dongle)) == count

    # A block that answered keeps its values and its interval over a failure.
    for address in range(0x102A, 0x1032):
        del hp_dongle.registers[address]
    coordinator._energy_due[(0x102A, 8)] = 0.0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert 0x102A in coordinator.energy_errors
    assert float(state(hass, entry, "load_usage_today").state) == 0x30003
    assert coordinator._energy_due[(0x102A, 8)] - time.monotonic() < 301


async def test_hp_removes_old_debug_entities(hass, hp_dongle):
    """Debug sensors of 0.7.0 that got confirmed don't linger."""
    entry = MockConfigEntry(domain=DOMAIN, data=data_for(hp_dongle, "hp_inverter"))
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for address in ("300f", "3020"):
        registry.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_hp_debug_{address}",
            config_entry=entry,
        )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    ids = {e.unique_id for e in entities(hass, entry)}
    assert f"{entry.entry_id}_hp_debug_300f" not in ids
    assert f"{entry.entry_id}_hp_debug_3020" in ids


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
    coordinator._energy_due = dict.fromkeys(coordinator._energy_due, float("inf"))
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
