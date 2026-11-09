# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""DryingPilot sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfPressure
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import DryingPilotConfigEntry, DryingPilotCoordinator, DryerData
from .entity import DryingPilotEntity
from .model import (
    Category,
    Location,
    Mode,
    apply_local_correction,
    forecast_series,
    next_opportunity,
    predry_windows,
)
from .texts import pct


@dataclass(frozen=True, kw_only=True)
class DryerSensorDescription(SensorEntityDescription):
    value_fn: Callable[[DryerData], Any]


def _progress(d: DryerData) -> int | None:
    ev = d.evaluation
    return pct(ev.progress, ev.target) if ev.progress is not None else None


def _window_start(d: DryerData) -> datetime | None:
    w = d.evaluation.next_window
    return w.start if w else None


def _window_end(d: DryerData) -> datetime | None:
    w = d.evaluation.next_window
    return w.end if w else None


SENSORS: tuple[DryerSensorDescription, ...] = (
    DryerSensorDescription(
        key="mode",
        device_class=SensorDeviceClass.ENUM,
        options=[m.value for m in Mode],
        value_fn=lambda d: d.evaluation.mode.value,
    ),
    DryerSensorDescription(
        key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[c.value for c in Category],
        value_fn=lambda d: d.evaluation.category.value,
    ),
    DryerSensorDescription(
        key="rate",
        native_unit_of_measurement="%/h",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: round(d.evaluation.rate, 2),
    ),
    DryerSensorDescription(
        key="vpd",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: round(d.evaluation.vpd, 2),
    ),
    DryerSensorDescription(
        key="progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_progress,
    ),
    DryerSensorDescription(
        key="possible_until",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.evaluation.possible_until,
    ),
    DryerSensorDescription(
        key="dry_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.evaluation.dry_at,
    ),
    DryerSensorDescription(
        key="next_window_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_window_start,
    ),
    DryerSensorDescription(
        key="next_window_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_window_end,
    ),
    DryerSensorDescription(
        key="next_opportunity",
        device_class=SensorDeviceClass.ENUM,
        options=["window", "pre_dry", "none"],
        value_fn=lambda d: next_opportunity(d.evaluation, dt_util.utcnow())[0],
    ),
    DryerSensorDescription(
        key="calibration",
        device_class=SensorDeviceClass.ENUM,
        options=["off", "learning", "calibrated"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: None,  # filled in by the entity (needs coordinator)
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DryingPilotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(DryerSensor(coordinator, desc) for desc in SENSORS)


class DryerSensor(DryingPilotEntity, SensorEntity):
    entity_description: DryerSensorDescription
    _unrecorded_attributes = frozenset({"forecast", "windows"})

    def __init__(
        self, coordinator: DryingPilotCoordinator, desc: DryerSensorDescription
    ) -> None:
        super().__init__(coordinator, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> Any:
        if self.entity_description.key == "calibration":
            return self._calibration_state()
        return self.entity_description.value_fn(self.coordinator.data)

    def _calibration_state(self) -> str:
        c = self.coordinator
        if not c.state.calibration_enabled:
            return "off"
        result = c.calibration.get(c.state.location)
        return "calibrated" if result and result.calibrated else "learning"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        d = self.coordinator.data
        key = self.entity_description.key
        if key == "next_opportunity":
            kind, w = next_opportunity(d.evaluation, dt_util.utcnow())
            if w is None:
                return {"start": None, "end": None, "gain": None}
            return {
                "start": w.start.isoformat(),
                "end": w.end.isoformat(),
                "gain": pct(w.total, d.evaluation.target),
            }
        if key == "mode":
            return {
                "title": d.tile.title,
                "subtitle": d.tile.subtitle,
                "tile_icon": d.tile.icon,
                "color": d.tile.color,
                "hanging": d.state.hanging,
                "progress": _progress(d),
                "location": d.state.location.value,
                "laundry_type": d.state.laundry.value,
                "bring_in_reason": (
                    d.evaluation.bring_in_reason.value
                    if d.evaluation.bring_in_reason
                    else None
                ),
                "live_sensors": d.live is not None,
                "live_source": self.coordinator.live_source,
                "question": d.state.question,
                "calibration_enabled": d.state.calibration_enabled,
                "ask_on_stop": self.coordinator.asks_feedback,
                "humid": d.state.humid,
            }
        if key == "calibration":
            attrs: dict[str, Any] = {}
            for loc in Location:
                r = self.coordinator.calibration.get(loc)
                if r is None:
                    continue
                attrs[f"{loc.value}_k"] = round(r.k, 3)
                attrs[f"{loc.value}_wind_factor"] = round(r.wind_factor, 3)
                attrs[f"{loc.value}_uncertainty_pct"] = round(100 * r.k_uncertainty)
                attrs[f"{loc.value}_answers"] = r.answers
                attrs[f"{loc.value}_runs"] = r.runs
            since = self.coordinator.calibration_since
            attrs["since"] = since.isoformat() if since else None
            attrs["stored_runs"] = len(self.coordinator.history)
            return attrs
        if key == "rate":
            return {"forecast": self._forecast_series(d), "windows": self._windows(d)}
        if key == "progress":
            ev = d.evaluation
            return {
                "progress_at_window_end": (
                    pct(ev.progress_at_window_end, ev.target)
                    if ev.progress_at_window_end is not None
                    else None
                ),
                "window_end": ev.window_end.isoformat() if ev.window_end else None,
                "started_at": (
                    d.state.started_at.isoformat() if d.state.started_at else None
                ),
                "dry_since": (
                    d.state.dry_since.isoformat() if d.state.dry_since else None
                ),
            }
        return None

    def _forecast_series(self, d: DryerData) -> list[dict[str, Any]]:
        """Hourly rate, rain and humidity level for the card strip and charts."""
        params = self.coordinator.params_for(d.state.location)
        now = dt_util.utcnow()
        slots = apply_local_correction(d.slots, now, d.live, params)
        return forecast_series(
            slots,
            now,
            d.live,
            d.state.location,
            params,
            d.state.humid,
            target=params.target(d.state.laundry),
        )

    def _windows(self, d: DryerData) -> list[dict[str, Any]]:
        predry = predry_windows(
            d.evaluation.windows, dt_util.utcnow(), d.evaluation.target, self.coordinator.params
        )
        return [
            {
                "start": w.start.isoformat(),
                "end": w.end.isoformat(),
                "progress": pct(w.total, d.evaluation.target),
                "sufficient": w.sufficient,
                "predry": w in predry,
            }
            for w in d.evaluation.windows
        ]
