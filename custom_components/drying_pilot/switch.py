# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Switch to turn self-calibration on or off."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DryingPilotConfigEntry
from .entity import DryingPilotEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DryingPilotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([CalibrationSwitch(entry.runtime_data, "calibration_enabled")])


class CalibrationSwitch(DryingPilotEntity, SwitchEntity):
    """When off, DryingPilot asks no questions and uses the default factors."""

    _attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool:
        return self.coordinator.state.calibration_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_calibration(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_calibration(False)
