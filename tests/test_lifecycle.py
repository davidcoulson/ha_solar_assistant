import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components import solar_assistant as integration


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("platform import failed"), asyncio.CancelledError()])
async def test_failed_setup_stops_owned_task_and_clears_data(hass, entry, monkeypatch, error):
    tasks = []
    def create_task(hass_arg, coroutine, name):
        assert hass_arg is hass
        task = asyncio.create_task(coroutine, name=name)
        tasks.append(task)
        return task
    entry.async_create_background_task.side_effect = create_task
    hass.config_entries.async_forward_entry_setups.side_effect = error
    monkeypatch.setattr(integration.SolarAssistantCoordinator, "_session_once", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(type(error)):
        await integration.async_setup_entry(hass, entry)
    assert entry.entry_id not in hass.data[integration.DOMAIN]
    assert len(tasks) == 1 and tasks[0].done()

    # A retry owns just one new task; normal unload also stops it.
    hass.config_entries.async_forward_entry_setups.side_effect = None
    entry.add_update_listener = Mock(return_value=lambda: None)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    assert await integration.async_setup_entry(hass, entry)
    assert await integration.async_unload_entry(hass, entry)
    assert all(task.done() for task in tasks)
    assert entry.entry_id not in hass.data[integration.DOMAIN]
