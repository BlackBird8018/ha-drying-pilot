# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Location and laundry type selects."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DryingPilotConfigEntry
from .entity import DryingPilotEntity
from .model import LaundryType, Location


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DryingPilotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            LocationSelect(coordinator, "location"),
            LaundrySelect(coordinator, "laundry_type"),
        ]
    )


class LocationSelect(DryingPilotEntity, SelectEntity):
    _attr_options = [loc.value for loc in Location]

    @property
    def current_option(self) -> str:
        return self.coordinator.state.location.value

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_location(Location(option))


class LaundrySelect(DryingPilotEntity, SelectEntity):
    _attr_options = [t.value for t in LaundryType]

    @property
    def current_option(self) -> str:
        return self.coordinator.state.laundry.value

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_laundry(LaundryType(option))
