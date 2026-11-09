# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Buttons "hung up" and "brought in"."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DryingPilotConfigEntry
from .entity import DryingPilotEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DryingPilotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [StartButton(coordinator, "start"), StopButton(coordinator, "stop")]
    )


class StartButton(DryingPilotEntity, ButtonEntity):
    """Starts with the currently selected location and laundry type."""

    async def async_press(self) -> None:
        await self.coordinator.async_start()


class StopButton(DryingPilotEntity, ButtonEntity):
    async def async_press(self) -> None:
        await self.coordinator.async_stop()
