"""Small HA API fakes for offline unit tests; no HA instance is started."""
import socket
import sys
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def module(name, **attrs):
    mod = ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


class Flow:
    def __init_subclass__(cls, **kwargs):
        pass

    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}


class Entity:
    _attr_native_min_value = 0
    _attr_native_max_value = 100

    async def async_added_to_hass(self):
        pass


class Disabler(Enum):
    INTEGRATION = "integration"
    USER = "user"


module("homeassistant")
module("homeassistant.config_entries", ConfigEntry=object, ConfigFlow=Flow,
       OptionsFlow=Flow, ConfigFlowResult=dict)
module("homeassistant.core", HomeAssistant=object, callback=lambda f: f)
module("homeassistant.exceptions", HomeAssistantError=type("HomeAssistantError", (Exception,), {}))
module("homeassistant.data_entry_flow", section=lambda schema, options: schema)
module("homeassistant.helpers")
module("homeassistant.helpers.selector")
module("homeassistant.helpers.entity_registry", RegistryEntryDisabler=Disabler)
module("homeassistant.helpers.dispatcher", async_dispatcher_send=Mock(),
       async_dispatcher_connect=Mock(return_value=lambda: None))
module("homeassistant.helpers.entity", Entity=Entity, DeviceInfo=dict,
       EntityCategory=SimpleNamespace(DIAGNOSTIC="diagnostic"))
module("homeassistant.helpers.device_registry", DeviceEntryType=SimpleNamespace(SERVICE="service"))
module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
module("homeassistant.util")
module("homeassistant.util.dt", utcnow=lambda: datetime.now(timezone.utc))
module("homeassistant.components")
module("homeassistant.components.zeroconf", async_get_instance=AsyncMock())
for platform in ("sensor", "number", "select", "switch"):
    module(f"homeassistant.components.{platform}", **{f"{platform.title()}Entity": type(platform, (Entity,), {})})


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Network access forbidden in offline tests")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket.socket, "sendto", blocked)


@pytest.fixture
def entry():
    return SimpleNamespace(data={"auth_method": "local", "host": "unit.example",
                                 "password": "secret"}, options={}, entry_id="test",
                           title="Unit", unique_id="local:unit.example",
                           async_start_reauth=Mock(), async_on_unload=Mock(),
                           async_create_background_task=Mock())


@pytest.fixture
def hass():
    return SimpleNamespace(data={}, config_entries=SimpleNamespace(
        async_update_entry=Mock(), async_entries=Mock(return_value=[]),
        async_forward_entry_setups=AsyncMock(), async_reload=AsyncMock()),
        async_add_executor_job=AsyncMock(return_value=None),
        # Run the coordinator's coalesced dispatch (call_soon) immediately.
        loop=SimpleNamespace(call_soon=lambda fn, *args: fn(*args)))


@pytest.fixture
def coordinator(hass, entry):
    from custom_components.solar_assistant.coordinator import SolarAssistantCoordinator
    return SolarAssistantCoordinator(hass, entry)
