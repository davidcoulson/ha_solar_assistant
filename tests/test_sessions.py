import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.solar_assistant import coordinator as coord
from custom_components.solar_assistant.entity import SolarAssistantMetricEntity


def metric(topic="inverter_1/power", **changes):
    attrs = dict(topic=topic, device="inverters", number=0, group="Status", name="Power",
                 value=500, unit="W", platform="sensor", device_class="power",
                 state_class="measurement", unit_of_measurement="W", min=None, max=None,
                 options=None, payload_on=None, payload_off=None)
    return SimpleNamespace(**(attrs | changes))


def fake_socket():
    return Mock(connected_host="unit.example", subscribe_metrics=AsyncMock(),
                subscribe_system_metrics=AsyncMock(), listen=AsyncMock(), close=AsyncMock())


@pytest.mark.asyncio
async def test_reconnect_requires_fresh_topic(coordinator, monkeypatch):
    m = metric()
    coordinator._on_metric(m)
    entity = SolarAssistantMetricEntity(coordinator, coordinator.entry, m.topic, coordinator.definitions[m.topic])
    assert entity.available
    sock = fake_socket()
    async def listen():
        assert not entity.available
        coordinator._on_metric(metric("inverter_2/power"))
        assert not entity.available
        coordinator._on_metric(m)
        assert entity.available
    sock.listen.side_effect = listen
    monkeypatch.setattr(coord, "connect", AsyncMock(return_value=sock))
    coordinator._rest_discovery = AsyncMock()
    coordinator._store_site_id = AsyncMock()
    await coordinator._session_once()
    assert not entity.available


@pytest.mark.asyncio
async def test_snapshots_expire_omitted_topics(coordinator):
    old = metric()
    coordinator._on_metric(old)
    coordinator._fetch_discovery = AsyncMock(return_value=[metric("inverter_2/power")])
    await coordinator._rest_discovery()
    assert old.topic not in coordinator.data
    assert old.topic not in coordinator.last_update
    system = metric("system/temp", device="system")
    coordinator._on_system_metrics([system])
    coordinator._on_system_metrics([])
    assert system.topic not in coordinator.data
    assert system.topic not in coordinator.last_update


@pytest.mark.asyncio
async def test_short_clean_close_keeps_failure_timer_and_backoff(coordinator, monkeypatch):
    sock = fake_socket()
    coordinator._rest_discovery = AsyncMock()
    coordinator._store_site_id = AsyncMock()
    coordinator._recover_ip = AsyncMock()
    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    coordinator._first_failure_at = start
    monkeypatch.setattr(coord, "connect", AsyncMock(return_value=sock))
    delays = []
    async def sleep(delay):
        delays.append(delay)
        assert not coordinator.is_connected
        if len(delays) == 3:
            raise asyncio.CancelledError
    monkeypatch.setattr(coord.asyncio, "sleep", sleep)
    await coordinator._run()
    assert delays == [5, 10, 20]
    assert coordinator._first_failure_at == start
    coordinator._recover_ip.assert_awaited_once()
    assert sock.close.await_count == 3


@pytest.mark.asyncio
async def test_data_session_resets_failure_timer(coordinator, monkeypatch):
    sock = fake_socket()
    sock.listen.side_effect = lambda: coordinator._on_metric(metric())
    coordinator._rest_discovery = AsyncMock()
    coordinator._store_site_id = AsyncMock()
    coordinator._first_failure_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(coord, "connect", AsyncMock(return_value=sock))
    monkeypatch.setattr(coord.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError))
    await coordinator._run()
    assert coordinator._first_failure_at is None
