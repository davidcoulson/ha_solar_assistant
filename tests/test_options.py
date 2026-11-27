from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components import solar_assistant as integration
from custom_components.solar_assistant import config_flow as flow
from tests.test_sessions import metric


@pytest.mark.asyncio
@pytest.mark.parametrize("submission, expected", [
    ({}, ["battery_*/power", "total/*"]),
    ({"totals": {"topics": []}}, ["battery_*/power"]),
    ({"totals": {"topics": ["total/power"]}}, ["battery_*/power", "total/power"]),
])
async def test_options_merge_omitted_sections(entry, submission, expected):
    entry.options = {"enabled_topics": ["total/*", "battery_*/power"], "other": True}
    f = flow.SolarAssistantOptionsFlow(entry)
    f._discover_metrics = AsyncMock(return_value=[metric("total/power", device="totals")])
    result = await f.async_step_init(submission)
    assert result["data"] == {"enabled_topics": expected, "other": True, "min_update_interval_s": 0}


@pytest.mark.asyncio
async def test_options_preserve_registry_customizations(coordinator, monkeypatch):
    entry, hass = coordinator.entry, coordinator.hass
    entry.options = {"enabled_topics": ["total/power", "total/user_disabled"]}
    topics = ["excluded", "missing", "power", "user_disabled"]
    disabled = [None, None, integration.er.RegistryEntryDisabler.INTEGRATION,
                integration.er.RegistryEntryDisabler.USER]
    entities = [SimpleNamespace(domain="sensor", unique_id=f"{entry.unique_id}_total/{topic}",
                                entity_id=f"sensor.{topic}", disabled_by=why)
                for topic, why in zip(topics, disabled)]
    coordinator.definitions = {f"total/{t}": {} for t in topics if t != "missing"}
    hass.data = {"solar_assistant": {entry.entry_id: coordinator}}
    registry = Mock()
    monkeypatch.setattr(integration.er, "async_get", Mock(return_value=registry), raising=False)
    monkeypatch.setattr(integration.er, "async_entries_for_config_entry", Mock(return_value=entities), raising=False)
    await integration._async_options_updated(hass, entry)
    assert registry.async_update_entity.call_args_list == [
        (("sensor.excluded",), {"disabled_by": integration.er.RegistryEntryDisabler.INTEGRATION}),
        (("sensor.power",), {"disabled_by": None}),
    ]
    registry.async_remove.assert_not_called()
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
