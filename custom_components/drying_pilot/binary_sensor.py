# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Binary sensors "bring in" and "dry"."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DryingPilotConfigEntry
from .entity import DryingPilotEntity
from .model import Mode


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DryingPilotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [
            BringInSensor(coordinator, "bring_in"),
            DrySensor(coordinator, "dry"),
        ]
    )


class BringInSensor(DryingPilotEntity, BinarySensorEntity):
    """On when hanging laundry should come in because of rain or humidity."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.evaluation.bring_in

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        reason = self.coordinator.data.evaluation.bring_in_reason
        return {"reason": reason.value if reason else None}


class DrySensor(DryingPilotEntity, BinarySensorEntity):
    """On when the hanging laundry is expected to be dry."""

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.evaluation.mode is Mode.DRY
