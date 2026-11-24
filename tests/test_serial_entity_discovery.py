"""Tests for adding serial gateway entities as their values are reported."""

from types import SimpleNamespace
from unittest.mock import patch

from pyotgw.vars import BOILER, DATA_CH_WATER_TEMP, DATA_RETURN_WATER_TEMP, DATA_SLAVE_FLAME_ON, OTGW, OTGW_THRM_DETECT, THERMOSTAT

from custom_components.sat.coordinator.serial import binary_sensor as serial_binary_sensor
from custom_components.sat.coordinator.serial import sensor as serial_sensor


def _status(boiler: dict, thermostat: dict | None = None, thermostat_detect: str = "D") -> dict:
    return {BOILER: boiler, THERMOSTAT: thermostat or {}, OTGW: {OTGW_THRM_DETECT: thermostat_detect}}


THERMOSTAT_DETECT_SENSOR = (OTGW, OTGW_THRM_DETECT)


class FakeCoordinator:
    def __init__(self, data: dict) -> None:
        self.data = data
        self.listeners = []

    def async_add_listener(self, listener):
        self.listeners.append(listener)
        return lambda: self.listeners.remove(listener)

    def report(self, data: dict) -> None:
        self.data = data
        for listener in list(self.listeners):
            listener()


class FakeConfigEntry:
    entry_id = "entry"

    def __init__(self) -> None:
        self.unload_callbacks = []

    def async_on_unload(self, unload_callback) -> None:
        self.unload_callbacks.append(unload_callback)


def test_only_reported_values_become_sensors():
    data = _status({DATA_CH_WATER_TEMP: 45.0})

    definitions = serial_sensor.newly_reported_sensor_definitions(data, added={THERMOSTAT_DETECT_SENSOR})

    assert [(definition.source, definition.key) for definition in definitions] == [(BOILER, DATA_CH_WATER_TEMP)]


def test_already_added_sensors_are_not_repeated():
    data = _status({DATA_CH_WATER_TEMP: 45.0, DATA_RETURN_WATER_TEMP: 38.0})

    definitions = serial_sensor.newly_reported_sensor_definitions(data, added={THERMOSTAT_DETECT_SENSOR, (BOILER, DATA_CH_WATER_TEMP)})

    assert [definition.key for definition in definitions] == [DATA_RETURN_WATER_TEMP]


def test_thermostat_values_are_ignored_without_a_thermostat():
    data = _status({}, thermostat={DATA_CH_WATER_TEMP: 45.0}, thermostat_detect="D")

    assert serial_sensor.newly_reported_sensor_definitions(data, added={THERMOSTAT_DETECT_SENSOR}) == []


def test_thermostat_values_are_added_with_a_thermostat():
    data = _status({}, thermostat={DATA_CH_WATER_TEMP: 45.0}, thermostat_detect="I")

    definitions = serial_sensor.newly_reported_sensor_definitions(data, added={THERMOSTAT_DETECT_SENSOR})

    assert [(definition.source, definition.key) for definition in definitions] == [(THERMOSTAT, DATA_CH_WATER_TEMP)]


def test_binary_sensor_reported_as_false_is_added():
    data = _status({DATA_SLAVE_FLAME_ON: 0})

    definitions = serial_binary_sensor.newly_reported_binary_sensor_definitions(data, added=set())

    assert [definition.key for definition in definitions] == [DATA_SLAVE_FLAME_ON]


async def _setup_platform(module, entity_class_name: str, coordinator: FakeCoordinator, config_entry: FakeConfigEntry) -> list:
    added_entities = []
    entry_data = SimpleNamespace(coordinator=coordinator, config=None, heating_control=None)

    with (
        patch.object(module, "get_entry_data", return_value=entry_data),
        patch.object(module, entity_class_name, side_effect=lambda _coordinator, _config, _heating_control, definition: definition.key),
    ):
        await module.async_setup_entry(None, config_entry, added_entities.extend)

        coordinator.report(_status({DATA_CH_WATER_TEMP: 45.0, DATA_RETURN_WATER_TEMP: 38.0, DATA_SLAVE_FLAME_ON: 1}))
        coordinator.report(_status({DATA_CH_WATER_TEMP: 46.0, DATA_RETURN_WATER_TEMP: 39.0, DATA_SLAVE_FLAME_ON: 0}))

    return added_entities


async def test_sensors_reported_after_setup_are_added_once():
    coordinator = FakeCoordinator(_status({DATA_CH_WATER_TEMP: 44.0}))
    config_entry = FakeConfigEntry()

    added_entities = await _setup_platform(serial_sensor, "SatSensor", coordinator, config_entry)

    assert added_entities == [DATA_CH_WATER_TEMP, OTGW_THRM_DETECT, DATA_RETURN_WATER_TEMP]


async def test_binary_sensors_reported_after_setup_are_added_once():
    coordinator = FakeCoordinator(_status({}))
    config_entry = FakeConfigEntry()

    added_entities = await _setup_platform(serial_binary_sensor, "SatBinarySensor", coordinator, config_entry)

    assert added_entities == [DATA_SLAVE_FLAME_ON]


async def test_unloading_stops_adding_sensors():
    coordinator = FakeCoordinator(_status({}))
    config_entry = FakeConfigEntry()

    await _setup_platform(serial_sensor, "SatSensor", coordinator, config_entry)
    for unload_callback in config_entry.unload_callbacks:
        unload_callback()

    assert coordinator.listeners == []
