import asyncio
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
from py_solar_assistant import SolarAssistantError

from custom_components.solar_assistant import config_flow as flow
from custom_components.solar_assistant import coordinator as coord


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [SolarAssistantError(500, "failed"), aiohttp.ClientError(), TimeoutError(), OSError()])
async def test_site_id_failure_is_optional_and_rate_limited(coordinator, monkeypatch, error):
    lookup = AsyncMock(side_effect=error)
    monkeypatch.setattr(coord, "get_device_site_id", lookup)
    await coordinator._store_site_id()
    await coordinator._store_site_id()
    assert lookup.await_count == 1
    coordinator.hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_site_id_cancellation_propagates(coordinator, monkeypatch):
    monkeypatch.setattr(coord, "get_device_site_id", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await coordinator._store_site_id()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [SolarAssistantError(500, "failed"), aiohttp.ClientError(), TimeoutError(), OSError()])
async def test_local_setup_without_optional_site_id(hass, monkeypatch, error):
    f = flow.SolarAssistantConfigFlow()
    f.hass = hass
    f.async_set_unique_id = AsyncMock()
    f._abort_if_unique_id_configured = Mock()
    monkeypatch.setattr(flow, "connect", AsyncMock(return_value=Mock(close=AsyncMock())))
    monkeypatch.setattr(flow, "get_device_site_id", AsyncMock(side_effect=error))
    result = await f.async_step_local({"host": "unit.example", "password": "secret"})
    assert result["type"] == "create_entry"
    assert "site_id" not in result["data"]
