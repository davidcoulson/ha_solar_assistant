"""SolarAssistant numeric Settings entities (e.g. Max charge current, Max solar power)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import SolarAssistantCoordinator
from .entity import SolarAssistantMetricEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: SolarAssistantCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _on_new_metric(topic: str) -> None:
        if topic in known:
            return
        defn = coordinator.definitions.get(topic)
        if defn is None or defn.get("platform") != "number":
            return
        known.add(topic)
        async_add_entities([SolarAssistantNumber(coordinator, entry, topic, defn)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, coordinator.signal_new_metric, _on_new_metric)
    )

    for topic, defn in list(coordinator.definitions.items()):
        if defn.get("platform") != "number":
            continue
        if topic not in known:
            known.add(topic)
            async_add_entities([SolarAssistantNumber(coordinator, entry, topic, defn)])


class SolarAssistantNumber(SolarAssistantMetricEntity, NumberEntity):
    @property
    def device_class(self) -> str | None:
        return self._definition.get("device_class")

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self._definition.get("unit_of_measurement") or self._definition.get("unit") or None

    @property
    def native_min_value(self) -> float:
        value = self._definition.get("min")
        return float(value) if value is not None else super().native_min_value

    @property
    def native_max_value(self) -> float:
        value = self._definition.get("max")
        return float(value) if value is not None else super().native_max_value

    @property
    def native_value(self) -> float | None:
        v = self._coordinator.data.get(self._topic)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self._coordinator.set_setting(self._topic, value)
