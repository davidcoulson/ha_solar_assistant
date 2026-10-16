from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.solar_assistant import coordinator as coord
from custom_components.solar_assistant.number import SolarAssistantNumber
from custom_components.solar_assistant.select import SolarAssistantSelect
from custom_components.solar_assistant.sensor import SolarAssistantSensor
from custom_components.solar_assistant.switch import SolarAssistantSwitch
from tests.test_sessions import metric


@pytest.mark.parametrize("entity_class, changes, properties", [
    (SolarAssistantSelect, {"options": ["A", "B"]}, {"options": ["A", "B"]}),
    (SolarAssistantNumber, {"min": 2, "max": 20, "unit_of_measurement": "A", "device_class": "current"},
     {"native_min_value": 2, "native_max_value": 20, "native_unit_of_measurement": "A", "device_class": "current"}),
    (SolarAssistantSensor, {"unit_of_measurement": "A", "device_class": "current", "state_class": "total"},
     {"native_unit_of_measurement": "A", "device_class": "current", "state_class": "total"}),
])
def test_existing_entity_reads_new_definition(coordinator, entity_class, changes, properties):
    m = metric()
    coordinator._on_metric(m)
    entity = entity_class(coordinator, coordinator.entry, m.topic, coordinator.definitions[m.topic])
    entity.async_write_ha_state = Mock()
    coordinator._on_metric(metric(**changes))
    entity._on_update(m.topic)
    entity.async_write_ha_state.assert_called_once()
    for key, value in properties.items():
        assert getattr(entity, key) == value


@pytest.mark.asyncio
async def test_switch_uses_changed_payloads(coordinator):
    m = metric(value="yes-new", platform="switch")
    coordinator._on_metric(m)
    entity = SolarAssistantSwitch(coordinator, coordinator.entry, m.topic, coordinator.definitions[m.topic])
    coordinator._on_metric(metric(value="yes-new", platform="switch", payload_on="yes-new", payload_off="no-new"))
    assert entity.is_on
    coordinator.set_setting = AsyncMock()
    await entity.async_turn_on()
    coordinator.set_setting.assert_awaited_with(m.topic, "yes-new")
    await entity.async_turn_off()
    coordinator.set_setting.assert_awaited_with(m.topic, "no-new")


@pytest.mark.asyncio
async def test_rest_metadata_change_notifies_existing_sensor(coordinator, monkeypatch):
    m = metric()
    coordinator._on_metric(m)
    dispatch = Mock()
    monkeypatch.setattr(coord, "async_dispatcher_send", dispatch)
    coordinator._fetch_discovery = AsyncMock(return_value=[metric(unit="A")])
    await coordinator._rest_discovery()
    dispatch.assert_called_with(coordinator.hass, coordinator.signal_metric_update, frozenset({m.topic}))
    assert coordinator.definitions[m.topic]["unit"] == "A"
