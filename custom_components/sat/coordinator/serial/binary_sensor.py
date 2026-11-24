"""Binary Sensor platform for SAT."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional, cast

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity, ENTITY_ID_FORMAT
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import async_generate_entity_id
from pyotgw.vars import *

from . import TRANSLATE_SOURCE, SatSerialCoordinator
from ...entity import SatEntity
from ...entry_data import SatConfig, get_entry_data
from ...heating_control import SatHeatingControl

_LOGGER = logging.getLogger(__name__)


class SatBinarySensorInfo:
    def __init__(self, device_class: Optional[str], friendly_name_format: str, status_sources: list[str]):
        self.device_class = device_class
        self.status_sources = status_sources
        self.friendly_name_format = friendly_name_format


@dataclass(frozen=True, slots=True)
class SatSerialBinarySensorDefinition:
    info: SatBinarySensorInfo
    key: str
    source: str


BINARY_SENSOR_INFO: dict[str, SatBinarySensorInfo] = {
    DATA_MASTER_CH_ENABLED: SatBinarySensorInfo(None, "Thermostat Central Heating", [BOILER, THERMOSTAT]),
    DATA_MASTER_DHW_ENABLED: SatBinarySensorInfo(None, "Thermostat Hot Water", [BOILER, THERMOSTAT]),
    DATA_MASTER_COOLING_ENABLED: SatBinarySensorInfo(None, "Thermostat Cooling", [BOILER, THERMOSTAT]),
    DATA_MASTER_OTC_ENABLED: SatBinarySensorInfo(None, "Thermostat Outside Temperature Correction", [BOILER, THERMOSTAT]),
    DATA_MASTER_CH2_ENABLED: SatBinarySensorInfo(None, "Thermostat Central Heating 2", [BOILER, THERMOSTAT]),

    DATA_SLAVE_FAULT_IND: SatBinarySensorInfo(BinarySensorDeviceClass.PROBLEM, "Device Fault", [BOILER, THERMOSTAT]),
    DATA_SLAVE_CH_ACTIVE: SatBinarySensorInfo(BinarySensorDeviceClass.HEAT, "Device Central Heating", [BOILER, THERMOSTAT]),
    DATA_SLAVE_DHW_ACTIVE: SatBinarySensorInfo(BinarySensorDeviceClass.HEAT, "Device Hot Water", [BOILER, THERMOSTAT]),
    DATA_SLAVE_FLAME_ON: SatBinarySensorInfo(BinarySensorDeviceClass.HEAT, "Device Flame", [BOILER, THERMOSTAT]),
    DATA_SLAVE_COOLING_ACTIVE: SatBinarySensorInfo(BinarySensorDeviceClass.COLD, "Device Cooling", [BOILER, THERMOSTAT]),
    DATA_SLAVE_CH2_ACTIVE: SatBinarySensorInfo(BinarySensorDeviceClass.HEAT, "Device Central Heating 2", [BOILER, THERMOSTAT]),
    DATA_SLAVE_DIAG_IND: SatBinarySensorInfo(BinarySensorDeviceClass.PROBLEM, "Device Diagnostics", [BOILER, THERMOSTAT]),
    DATA_SLAVE_DHW_PRESENT: SatBinarySensorInfo(None, "Device Hot Water Present", [BOILER, THERMOSTAT]),
    DATA_SLAVE_CONTROL_TYPE: SatBinarySensorInfo(None, "Device Control Type", [BOILER, THERMOSTAT]),
    DATA_SLAVE_COOLING_SUPPORTED: SatBinarySensorInfo(None, "Device Cooling Support", [BOILER, THERMOSTAT]),
    DATA_SLAVE_DHW_CONFIG: SatBinarySensorInfo(None, "Device Hot Water Configuration", [BOILER, THERMOSTAT]),
    DATA_SLAVE_MASTER_LOW_OFF_PUMP: SatBinarySensorInfo(None, "Device Pump Commands Support", [BOILER, THERMOSTAT]),
    DATA_SLAVE_CH2_PRESENT: SatBinarySensorInfo(None, "Device Central Heating 2 Present", [BOILER, THERMOSTAT]),
    DATA_SLAVE_SERVICE_REQ: SatBinarySensorInfo(BinarySensorDeviceClass.PROBLEM, "Device Service Required", [BOILER, THERMOSTAT]),
    DATA_SLAVE_REMOTE_RESET: SatBinarySensorInfo(None, "Device Remote Reset Support", [BOILER, THERMOSTAT]),
    DATA_SLAVE_LOW_WATER_PRESS: SatBinarySensorInfo(BinarySensorDeviceClass.PROBLEM, "Device Low Water Pressure", [BOILER, THERMOSTAT]),
    DATA_SLAVE_GAS_FAULT: SatBinarySensorInfo(BinarySensorDeviceClass.PROBLEM, "Device Gas Fault", [BOILER, THERMOSTAT]),
    DATA_SLAVE_AIR_PRESS_FAULT: SatBinarySensorInfo(BinarySensorDeviceClass.PROBLEM, "Device Air Pressure Fault", [BOILER, THERMOSTAT]),
    DATA_SLAVE_WATER_OVERTEMP: SatBinarySensorInfo(BinarySensorDeviceClass.PROBLEM, "Device Water Over-temperature", [BOILER, THERMOSTAT]),
    DATA_REMOTE_TRANSFER_DHW: SatBinarySensorInfo(None, "Remote Hot Water Setpoint Transfer Support", [BOILER, THERMOSTAT]),
    DATA_REMOTE_TRANSFER_MAX_CH: SatBinarySensorInfo(None, "Remote Maximum Central Heating Setpoint Write Support", [BOILER, THERMOSTAT]),
    DATA_REMOTE_RW_DHW: SatBinarySensorInfo(None, "Remote Hot Water Setpoint Write Support", [BOILER, THERMOSTAT]),
    DATA_REMOTE_RW_MAX_CH: SatBinarySensorInfo(None, "Remote Central Heating Setpoint Write Support", [BOILER, THERMOSTAT]),
    DATA_ROVRD_MAN_PRIO: SatBinarySensorInfo(None, "Remote Override Manual Change Priority", [BOILER, THERMOSTAT]),
    DATA_ROVRD_AUTO_PRIO: SatBinarySensorInfo(None, "Remote Override Program Change Priority", [BOILER, THERMOSTAT]),

    OTGW_GPIO_A_STATE: SatBinarySensorInfo(None, "Gateway GPIO A", [OTGW]),
    OTGW_GPIO_B_STATE: SatBinarySensorInfo(None, "Gateway GPIO B", [OTGW]),
    OTGW_IGNORE_TRANSITIONS: SatBinarySensorInfo(None, "Gateway Ignore Transitions", [OTGW]),
    OTGW_OVRD_HB: SatBinarySensorInfo(None, "Gateway Override High Byte", [OTGW]),
}


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities) -> None:
    """Setup binary sensor platform."""
    entry_data = get_entry_data(hass, config_entry.entry_id)
    coordinator = cast(SatSerialCoordinator, entry_data.coordinator)
    added: set[tuple[str, str]] = set()

    @callback
    def add_newly_reported_binary_sensors() -> None:
        definitions = newly_reported_binary_sensor_definitions(coordinator.data, added)
        if not definitions:
            return

        added.update((definition.source, definition.key) for definition in definitions)
        async_add_entities([SatBinarySensor(coordinator, entry_data.config, entry_data.heating_control, definition) for definition in definitions])

    add_newly_reported_binary_sensors()

    # Right after connecting the gateway has only reported part of its values, so the rest are added as they arrive.
    config_entry.async_on_unload(coordinator.async_add_listener(add_newly_reported_binary_sensors))


def newly_reported_binary_sensor_definitions(data: Mapping[str, Mapping[str, Any]], added: set[tuple[str, str]]) -> list[SatSerialBinarySensorDefinition]:
    has_thermostat = data[OTGW].get(OTGW_THRM_DETECT) != "D"
    definitions = []

    for key, info in BINARY_SENSOR_INFO.items():
        for source in info.status_sources:
            if source == THERMOSTAT and not has_thermostat:
                continue

            if (source, key) in added or data[source].get(key) is None:
                continue

            definitions.append(SatSerialBinarySensorDefinition(key=key, info=info, source=source))

    return definitions


class SatBinarySensor(SatEntity, BinarySensorEntity):
    _attr_should_poll = False

    def __init__(
            self,
            coordinator: SatSerialCoordinator,
            config: SatConfig,
            heating_control: SatHeatingControl,
            definition: SatSerialBinarySensorDefinition,
    ) -> None:
        super().__init__(coordinator, config, heating_control)

        self.entity_id = async_generate_entity_id(
            ENTITY_ID_FORMAT, f"{self._config.name_lower}_{definition.source}_{definition.key}", hass=coordinator.hass
        )

        self._key = definition.key
        self._source = definition.source
        self._device_class = definition.info.device_class

        friendly_name_format = definition.info.friendly_name_format
        if TRANSLATE_SOURCE[definition.source] is not None:
            friendly_name_format = f"{friendly_name_format} ({TRANSLATE_SOURCE[definition.source]})"

        self._friendly_name = friendly_name_format

    @property
    def name(self):
        """Return the friendly name of the sensor."""
        return self._friendly_name

    @property
    def device_class(self):
        """Return the device class."""
        return self._device_class

    @property
    def available(self):
        """Return availability of the sensor."""
        return self._coordinator.data[self._source].get(self._key) is not None

    @property
    def is_on(self):
        """Return the state of the device."""
        return self._coordinator.data[self._source].get(self._key)

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{self._config.entry_id}-{self._source}-{self._key}"
