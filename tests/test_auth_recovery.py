from unittest.mock import AsyncMock, Mock

import pytest
from py_solar_assistant import ConnectError, SolarAssistantError

from custom_components.solar_assistant import config_flow as flow
from custom_components.solar_assistant import coordinator as coord


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["local", "cloud"])
async def test_mdns_hint_never_receives_credentials(coordinator, monkeypatch, method):
    coordinator.entry.data.update(auth_method=method, site_id=42)
    coordinator._mdns_find_ip = AsyncMock(return_value="192.0.2.99")
    coordinator._refresh_cloud_token = AsyncMock()
    dial = AsyncMock()
    monkeypatch.setattr(coord, "connect", dial)
    await coordinator._recover_ip()
    coordinator.hass.config_entries.async_update_entry.assert_not_called()
    dial.assert_not_called()
    assert coordinator.entry.data["host"] == "unit.example"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_local_rejection_starts_reauth(coordinator, monkeypatch, status):
    coordinator._rest_discovery = AsyncMock()
    coordinator._store_site_id = AsyncMock()
    monkeypatch.setattr(coord, "connect", AsyncMock(side_effect=ConnectError(str(status))))
    await coordinator._run()
    coordinator.entry.async_start_reauth.assert_called_once_with(coordinator.hass)
    assert coordinator._stopping


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 503])
async def test_cloud_refresh_auth_vs_transient(coordinator, monkeypatch, status):
    coordinator.entry.data.update(auth_method="cloud", site_id=42, api_key="old")
    coordinator._session_once = AsyncMock(side_effect=coord._ReauthRequired("401"))
    client = Mock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False))
    monkeypatch.setattr(coord, "SolarAssistantClient", Mock(return_value=client))
    monkeypatch.setattr(coord, "authorize_site", AsyncMock(side_effect=SolarAssistantError(status, "failed")))
    monkeypatch.setattr(coord.asyncio, "sleep", AsyncMock(side_effect=__import__('asyncio').CancelledError))
    await coordinator._run()
    assert coordinator.entry.async_start_reauth.call_count == (0 if status == 503 else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["local", "cloud"])
@pytest.mark.parametrize("step", ["reauth_confirm", "reconfigure"])
async def test_update_validates_and_preserves_identity(entry, hass, monkeypatch, method, step):
    entry.data.update(auth_method=method, site_id=42, api_key="old")
    f = flow.SolarAssistantConfigFlow()
    f.hass = hass
    f._get_reauth_entry = Mock(return_value=entry)
    f._get_reconfigure_entry = Mock(return_value=entry)
    f.async_update_reload_and_abort = Mock(return_value={"type": "abort"})
    sock = Mock(close=AsyncMock())
    dial = AsyncMock(return_value=sock)
    monkeypatch.setattr(flow, "connect", dial)
    client = Mock(__aenter__=AsyncMock(), __aexit__=AsyncMock(return_value=False))
    monkeypatch.setattr(flow, "SolarAssistantClient", Mock(return_value=client))
    monkeypatch.setattr(flow, "authorize_site", AsyncMock(return_value=Mock(
        host="cloud.example", local_ip="192.0.2.1", token="new-token", site_key="key")))
    assert (await getattr(f, f"async_step_{step}")())["type"] == "form"
    submitted = {"password": "new", "api_key": "new-key", "host": "trusted.example", "local_ip": "192.0.2.2"}
    await getattr(f, f"async_step_{step}")(submitted)
    data = f.async_update_reload_and_abort.call_args.kwargs["data"]
    assert data["site_id"] == 42
    assert entry.unique_id == "local:unit.example"
    assert entry.data["password"] == "secret"
    if method == "local":
        assert data["password"] == "new"
        assert dial.call_args.args[0].local_ip == ("trusted.example" if step == "reconfigure" else "unit.example")
    else:
        assert data["api_key"] == "new-key"
        assert data["token"] == "new-token"
    sock.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalid_reauth_does_not_update(entry, monkeypatch):
    f = flow.SolarAssistantConfigFlow()
    f._get_reauth_entry = Mock(return_value=entry)
    f.async_update_reload_and_abort = Mock()
    monkeypatch.setattr(flow, "connect", AsyncMock(side_effect=ConnectError("401")))
    result = await f.async_step_reauth_confirm({"password": "wrong"})
    assert result["errors"] == {"base": "invalid_auth"}
    f.async_update_reload_and_abort.assert_not_called()
