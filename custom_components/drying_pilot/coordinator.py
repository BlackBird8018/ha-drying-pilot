# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""Coordinator: fetches measurements and forecast, tracks progress, evaluates,
asks for feedback and calibrates."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .calibration import (
    MAX_RUN_DURATION,
    MAX_RUNS,
    CalibrationResult,
    Observation,
    Run,
    Sample,
    fit,
    progress_from_trace,
)
from .const import (
    CONF_A,
    CONF_B,
    CONF_CALIBRATION_SINCE,
    CONF_DEW_MARGIN,
    CONF_HUMIDITY,
    CONF_MIN_RATE,
    CONF_NOTIFY_TARGETS,
    CONF_NOTIFY_TYPES,
    CONF_PV_PEAK,
    CONF_PREDRY_MIN_HOURS,
    CONF_PV_POWER,
    CONF_RAIN_MM,
    CONF_RAIN_PROBABILITY,
    CONF_REWET_RH,
    CONF_REWET_RH_EXIT,
    CONF_SPIN_RPM,
    CONF_SUN_GAIN,
    CONF_TARGET_HEAVY,
    CONF_TARGET_LIGHT,
    CONF_TARGET_NORMAL,
    CONF_TEMPERATURE,
    CONF_WEATHER,
    DEFAULT_PV_PEAK,
    DOMAIN,
    FEEDBACK_SNOOZE,
    FORECAST_INTERVAL,
    HUMID_MIN_DURATION,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .model import (
    Evaluation,
    LaundryType,
    Location,
    Mode,
    ModelParams,
    Slot,
    Weather,
    advance_progress,
    dew_point,
    drying_rate,
    evaluate,
    humid_enter,
    humid_exit,
    humidity_from_dew_point,
    is_raining,
    slots_from_forecast,
    spin_factor,
    sun_from_pv,
)
from .notify import (
    DEFAULT_NOTIFY_TYPES,
    Notification,
    NotifyType,
    due_notifications,
    feedback_question,
)
from .texts import TileText, tile_text

_LOGGER = logging.getLogger(__name__)

type DryingPilotConfigEntry = ConfigEntry[DryingPilotCoordinator]

QUESTION_DRY_CHECK = "dry_check"
ANSWERS = ("dry", "damp", "unknown", "later")


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _dt(value: Any) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


@dataclass
class DryerState:
    """Persistent state (survives restarts)."""

    hanging: bool = False
    location: Location = Location.LINE
    laundry: LaundryType = LaundryType.NORMAL
    progress: float = 0.0
    started_at: datetime | None = None
    dry_since: datetime | None = None
    last_tick: datetime | None = None
    last_rate: float | None = None
    notified: list[str] = field(default_factory=list)
    last_good_window: date | None = None
    last_predry_window: date | None = None
    # humidity debounce
    humid: bool = False
    humid_candidate_since: datetime | None = None
    # feedback / calibration
    calibration_enabled: bool = True
    question: str | None = None
    question_asked_at: datetime | None = None
    snooze_until: datetime | None = None
    no_more_questions: bool = False
    feedback_round: int = 0
    run: Run | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "hanging": self.hanging,
            "location": self.location.value,
            "laundry": self.laundry.value,
            "progress": self.progress,
            "started_at": _iso(self.started_at),
            "dry_since": _iso(self.dry_since),
            "last_tick": _iso(self.last_tick),
            "last_rate": self.last_rate,
            "notified": list(self.notified),
            "last_good_window": (
                self.last_good_window.isoformat() if self.last_good_window else None
            ),
            "last_predry_window": (
                self.last_predry_window.isoformat() if self.last_predry_window else None
            ),
            "humid": self.humid,
            "humid_candidate_since": _iso(self.humid_candidate_since),
            "calibration_enabled": self.calibration_enabled,
            "question": self.question,
            "question_asked_at": _iso(self.question_asked_at),
            "snooze_until": _iso(self.snooze_until),
            "no_more_questions": self.no_more_questions,
            "feedback_round": self.feedback_round,
            "run": self.run.to_dict() if self.run else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DryerState:
        try:
            return cls(
                hanging=bool(data.get("hanging", False)),
                location=Location(data.get("location", Location.LINE)),
                laundry=LaundryType(data.get("laundry", LaundryType.NORMAL)),
                progress=float(data.get("progress", 0.0)),
                started_at=_dt(data.get("started_at")),
                dry_since=_dt(data.get("dry_since")),
                last_tick=_dt(data.get("last_tick")),
                last_rate=data.get("last_rate"),
                notified=list(data.get("notified") or []),
                last_good_window=(
                    date.fromisoformat(data["last_good_window"])
                    if data.get("last_good_window")
                    else None
                ),
                last_predry_window=(
                    date.fromisoformat(data["last_predry_window"])
                    if data.get("last_predry_window")
                    else None
                ),
                humid=bool(data.get("humid", False)),
                humid_candidate_since=_dt(data.get("humid_candidate_since")),
                calibration_enabled=bool(data.get("calibration_enabled", True)),
                question=data.get("question"),
                question_asked_at=_dt(data.get("question_asked_at")),
                snooze_until=_dt(data.get("snooze_until")),
                no_more_questions=bool(data.get("no_more_questions", False)),
                feedback_round=int(data.get("feedback_round", 0)),
                run=Run.from_dict(data["run"]) if data.get("run") else None,
            )
        except (ValueError, TypeError, KeyError):
            return cls()


@dataclass(frozen=True)
class DryerData:
    """Result of an update, read by the entities."""

    evaluation: Evaluation
    tile: TileText
    live: Weather | None
    slots: list[Slot]
    state: DryerState


class DryingPilotCoordinator(DataUpdateCoordinator[DryerData]):
    """Central logic of the integration."""

    config_entry: DryingPilotConfigEntry

    def __init__(self, hass: HomeAssistant, entry: DryingPilotConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._history_store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}.history"
        )
        self.state = DryerState()
        self.history: list[Run] = []
        self.calibration: dict[Location, CalibrationResult] = {}
        self._forecast_raw: list[dict[str, Any]] = []
        self._forecast_fetched: datetime | None = None
        self._wind_factor = 1.0
        self.live_source: str | None = None

    # ------------------------------------------------------------ Configuration

    @property
    def _conf(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    @property
    def base_params(self) -> ModelParams:
        """Configured parameters without calibration factors."""
        c = self._conf
        d = ModelParams()
        spin = spin_factor(float(c.get(CONF_SPIN_RPM, 1400)))
        return ModelParams(
            a=float(c.get(CONF_A, d.a)),
            b=float(c.get(CONF_B, d.b)),
            sun_gain=float(c.get(CONF_SUN_GAIN, d.sun_gain)),
            min_rate=float(c.get(CONF_MIN_RATE, d.min_rate)),
            rain_mm=float(c.get(CONF_RAIN_MM, d.rain_mm)),
            rain_probability=float(c.get(CONF_RAIN_PROBABILITY, d.rain_probability)),
            rewet_rh=float(c.get(CONF_REWET_RH, d.rewet_rh)),
            rewet_rh_exit=float(c.get(CONF_REWET_RH_EXIT, d.rewet_rh_exit)),
            dew_margin=float(c.get(CONF_DEW_MARGIN, d.dew_margin)),
            predry_min_hours=float(c.get(CONF_PREDRY_MIN_HOURS, d.predry_min_hours)),
            targets={
                LaundryType.LIGHT: spin * float(c.get(CONF_TARGET_LIGHT, 70.0)),
                LaundryType.NORMAL: spin * float(c.get(CONF_TARGET_NORMAL, 100.0)),
                LaundryType.HEAVY: spin * float(c.get(CONF_TARGET_HEAVY, 150.0)),
            },
        )

    def params_for(self, location: Location) -> ModelParams:
        """Parameters including the learned factors for a location."""
        base = self.base_params
        cal = self.calibration.get(location)
        if not self.state.calibration_enabled or cal is None:
            return base
        return replace(base, k=cal.k, wind_factor=cal.wind_factor)

    @property
    def params(self) -> ModelParams:
        return self.params_for(self.state.location)

    @property
    def calibration_since(self) -> datetime | None:
        return _dt(self._conf.get(CONF_CALIBRATION_SINCE))

    # ------------------------------------------------------------ Lifecycle

    async def async_load(self) -> None:
        if (data := await self._store.async_load()) is not None:
            self.state = DryerState.from_dict(data)
        if (hist := await self._history_store.async_load()) is not None:
            runs = []
            for item in hist.get("runs", []):
                try:
                    runs.append(Run.from_dict(item))
                except (KeyError, TypeError, ValueError):
                    continue
            self.history = runs
        self._refit()

    def _save(self) -> None:
        self._store.async_delay_save(self.state.as_dict, 5)

    def _save_history(self) -> None:
        self._history_store.async_delay_save(
            lambda: {"runs": [r.to_dict() for r in self.history]}, 5
        )

    def _refit(self) -> None:
        runs = self.history + ([self.state.run] if self.state.run else [])
        self.calibration = {
            loc: fit(runs, loc, self.base_params, self.calibration_since)
            for loc in Location
        }

    # ------------------------------------------------------------ Actions

    async def async_start(
        self,
        location: Location | None = None,
        laundry: LaundryType | None = None,
    ) -> None:
        now = dt_util.utcnow()
        st = self.state
        if st.hanging and st.run:
            self._finish_run(now, None)
        if location is not None:
            st.location = location
        if laundry is not None:
            st.laundry = laundry
        st.hanging = True
        st.progress = 0.0
        st.started_at = now
        st.dry_since = None
        st.last_tick = now
        st.last_rate = None
        st.notified = []
        st.question = None
        st.question_asked_at = None
        st.snooze_until = None
        st.no_more_questions = False
        st.feedback_round = 0
        st.run = Run(
            start=now,
            location=st.location,
            laundry=st.laundry.value,
            target=self.base_params.target(st.laundry),
        )
        self._save()
        await self.async_refresh()

    async def async_stop(self, feedback: str | None = None) -> None:
        now = dt_util.utcnow()
        st = self.state
        if st.hanging:
            self._finish_run(now, feedback)
        st.hanging = False
        st.progress = 0.0
        st.started_at = None
        st.dry_since = None
        st.last_tick = None
        st.last_rate = None
        st.notified = []
        st.question = None
        st.question_asked_at = None
        st.snooze_until = None
        st.no_more_questions = False
        st.run = None
        self._save()
        await self.async_refresh()

    async def async_feedback(self, answer: str) -> None:
        """Answer to 'Is the laundry dry?'."""
        st = self.state
        if answer not in ANSWERS or not st.hanging or st.run is None:
            return
        now = dt_util.utcnow()
        st.question = None
        st.question_asked_at = None
        if answer == "later":
            st.snooze_until = now + FEEDBACK_SNOOZE
        elif answer == "unknown":
            st.no_more_questions = True
        elif answer == "dry":
            st.run.observations.append(Observation(now, True))
            st.no_more_questions = True
            self._refit()
        elif answer == "damp":
            st.run.observations.append(Observation(now, False))
            self._refit()
            params = self.params
            target = params.target(st.laundry)
            # "still damp" must not show as almost dry: 0.67 of the drying
            # potential corresponds to about 85 % displayed (two-phase curve)
            st.progress = min(progress_from_trace(st.run, now, params), 0.67 * target)
            st.dry_since = None
            st.feedback_round += 1
            st.last_tick = now
            st.last_rate = None
        self._save()
        await self.async_refresh()

    async def async_set_location(self, location: Location) -> None:
        self.state.location = location
        if self.state.run is not None:
            self.state.run.location = location
        self._save()
        await self.async_refresh()

    async def async_set_laundry(self, laundry: LaundryType) -> None:
        self.state.laundry = laundry
        if self.state.run is not None:
            self.state.run.laundry = laundry.value
            self.state.run.target = self.base_params.target(laundry)
        self._save()
        await self.async_refresh()

    async def async_set_calibration(self, enabled: bool) -> None:
        self.state.calibration_enabled = enabled
        if not enabled:
            self.state.question = None
        self._save()
        await self.async_refresh()

    def _finish_run(self, now: datetime, feedback: str | None) -> None:
        st = self.state
        run = st.run
        if run is None:
            return
        if (
            feedback in ("dry", "damp")
            and st.calibration_enabled
            and not (feedback == "dry" and st.no_more_questions)
        ):
            run.observations.append(Observation(now, feedback == "dry"))
        run.end = now
        if not st.calibration_enabled:
            run.excluded = "calibration_off"
        elif now - run.start > MAX_RUN_DURATION and not run.valid_observations():
            run.excluded = "too_long"
        self.history.append(run)
        self.history = self.history[-MAX_RUNS:]
        st.run = None
        self._save_history()
        self._refit()

    # ------------------------------------------------------------ Data fetching

    def _float_state(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        st = self.hass.states.get(entity_id)
        if st is None or st.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
            return None
        try:
            return float(st.state)
        except ValueError:
            return None

    def _weather_wind_kmh(self) -> float | None:
        """Current wind from the weather entity, in km/h."""
        st = self.hass.states.get(self._conf[CONF_WEATHER])
        if st is None:
            return None
        try:
            wind = float(st.attributes.get("wind_speed"))
        except (TypeError, ValueError):
            return None
        return wind * self._wind_factor

    def _update_wind_factor(self) -> None:
        st = self.hass.states.get(self._conf[CONF_WEATHER])
        unit = (st.attributes.get("wind_speed_unit") if st else None) or "km/h"
        self._wind_factor = {
            "m/s": 3.6,
            "mph": 1.609344,
            "kn": 1.852,
            "ft/s": 1.09728,
        }.get(unit, 1.0)

    async def _async_fetch_forecast(self, now: datetime) -> None:
        if (
            self._forecast_fetched is not None
            and now - self._forecast_fetched < FORECAST_INTERVAL
            and self._forecast_raw
        ):
            return
        entity_id = self._conf[CONF_WEATHER]
        try:
            resp = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            if not self._forecast_raw:
                raise UpdateFailed(f"Forecast unavailable: {err}") from err
            _LOGGER.warning("Forecast unavailable, using last one: %s", err)
            return
        forecast = (resp or {}).get(entity_id, {}).get("forecast", [])
        if forecast:
            self._forecast_raw = forecast
            self._forecast_fetched = now

    def _live_weather(self, slots: list[Slot], now: datetime) -> Weather | None:
        c = self._conf
        temp = self._float_state(c.get(CONF_TEMPERATURE))
        hum = self._float_state(c.get(CONF_HUMIDITY))
        current = next((s for s in slots if s.start <= now < s.end), None)
        self.live_source = None
        if temp is None:
            return None
        if hum is None:
            # Temperature only: derive humidity from the measured temperature
            # and the forecast dew point (changes much slower than RH)
            if current is None:
                return None
            fc = current.weather
            hum = humidity_from_dew_point(temp, dew_point(fc.temperature, fc.humidity))
            self.live_source = "temperature_dew_point"
        else:
            self.live_source = "sensors"
        wind = self._weather_wind_kmh()
        if wind is None:
            wind = current.weather.wind_kmh if current else 0.0
        pv = self._float_state(c.get(CONF_PV_POWER))
        if pv is not None:
            sun = sun_from_pv(pv, float(c.get(CONF_PV_PEAK, DEFAULT_PV_PEAK)))
        else:
            sun = current.weather.sun if current else 0.0
        return Weather(
            temperature=temp,
            humidity=hum,
            wind_kmh=wind,
            sun=sun,
            cloud=current.weather.cloud if current else None,
        )

    def _update_humid(self, current: Weather | None, now: datetime) -> bool:
        """Debounced humid state: hysteresis plus minimum duration."""
        st = self.state
        params = self.base_params
        if current is None:
            return st.humid
        if st.humid:
            if humid_exit(current, params):
                st.humid = False
                st.humid_candidate_since = None
        elif humid_enter(current, params):
            st.humid_candidate_since = st.humid_candidate_since or now
            if now - st.humid_candidate_since >= HUMID_MIN_DURATION:
                st.humid = True
        else:
            st.humid_candidate_since = None
        return st.humid

    # ------------------------------------------------------------ Notifications

    @property
    def _notify_targets(self) -> list[str]:
        return list(self._conf.get(CONF_NOTIFY_TARGETS) or [])

    @property
    def _notify_types(self) -> set[str]:
        return set(self._conf.get(CONF_NOTIFY_TYPES, DEFAULT_NOTIFY_TYPES))

    @property
    def asks_feedback(self) -> bool:
        st = self.state
        return st.hanging and st.calibration_enabled and not st.no_more_questions

    async def _async_notify(self, ev: Evaluation, now: datetime, tz) -> None:
        targets = self._notify_targets
        if not targets:
            return
        enabled = self._notify_types
        if self.asks_feedback:
            # the feedback question replaces the plain "dry" notification
            enabled.discard(NotifyType.DRY)
        st = self.state
        due = due_notifications(
            ev,
            st.hanging,
            enabled,
            set(st.notified),
            st.last_good_window,
            now,
            tz,
            self.hass.config.language,
            st.last_predry_window,
        )
        for note in due:
            if note.key == "good_window":
                st.last_good_window = now.astimezone(tz).date()
            elif note.key == "predry_window":
                st.last_predry_window = now.astimezone(tz).date()
            else:
                st.notified.append(note.key)
            await self._async_send_all(note)

    async def _async_send_all(self, note: Notification) -> None:
        for target in self._notify_targets:
            await self._async_send(target.removeprefix("notify."), note)

    async def _async_send(self, service: str, note: Notification) -> None:
        data: dict[str, Any] = {"tag": DOMAIN, "group": DOMAIN}
        if note.actions:
            data["actions"] = [
                {"action": action, "title": title} for action, title in note.actions
            ]
        try:
            await self.hass.services.async_call(
                "notify",
                service,
                {"title": note.title, "message": note.message, "data": data},
                blocking=False,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Notification to notify.%s failed: %s", service, err)

    async def _async_ask_feedback(self, ev: Evaluation, now: datetime) -> None:
        """Ask 'Is the laundry dry?' once DryingPilot expects it to be dry."""
        st = self.state
        if not self.asks_feedback or ev.mode is not Mode.DRY or st.question:
            return
        if st.snooze_until and now < st.snooze_until:
            return
        st.question = QUESTION_DRY_CHECK
        st.question_asked_at = now
        st.snooze_until = None
        if NotifyType.DRY in self._notify_types:
            key = f"feedback_{st.feedback_round}_{int(now.timestamp())}"
            await self._async_send_all(
                feedback_question(key, self.hass.config.language)
            )

    # ------------------------------------------------------------ Update

    async def _async_update_data(self) -> DryerData:
        now = dt_util.utcnow()
        st = self.state
        params = self.params
        self._update_wind_factor()
        await self._async_fetch_forecast(now)

        raw = [
            {**item, "wind_speed": (item.get("wind_speed") or 0) * self._wind_factor}
            for item in self._forecast_raw
        ]
        slots = slots_from_forecast(raw, params)
        live = self._live_weather(slots, now)
        current_slot = next((s for s in slots if s.start <= now < s.end), None)
        current = live or (current_slot.weather if current_slot else None)
        humid = self._update_humid(current, now)

        if st.hanging:
            # accumulate progress (trapezoid between previous and current rate)
            rate_now = drying_rate(current, st.location, params) if current else 0.0
            if st.last_tick is not None and now > st.last_tick:
                prev = st.last_rate if st.last_rate is not None else rate_now
                st.progress = advance_progress(
                    st.progress, (prev + rate_now) / 2, now - st.last_tick
                )
            st.last_tick = now
            st.last_rate = rate_now
            self._record(current, current_slot, now, humid)

        ev = evaluate(
            slots,
            now,
            live,
            st.location,
            st.laundry,
            params,
            hanging=st.hanging,
            progress=st.progress,
            humid_now=humid,
        )

        if st.hanging and ev.mode is Mode.DRY and st.dry_since is None:
            st.dry_since = now

        tz = dt_util.get_default_time_zone()
        await self._async_ask_feedback(ev, now)
        await self._async_notify(ev, now, tz)
        self._save()

        tile = tile_text(
            ev, st.location, now, tz, st.dry_since, self.hass.config.language
        )
        return DryerData(evaluation=ev, tile=tile, live=live, slots=slots, state=st)

    def _record(
        self,
        current: Weather | None,
        current_slot: Slot | None,
        now: datetime,
        humid: bool,
    ) -> None:
        """Add a sample to the running run and note rain / rewetting."""
        run = self.state.run
        if run is None or current is None:
            return
        run.add_sample(
            Sample(
                now,
                current.temperature,
                current.humidity,
                current.wind_kmh,
                current.sun,
                "sensor" if self.live_source else "forecast",
            )
        )
        raining = (
            run.location is Location.LINE
            and current_slot is not None
            and is_raining(current_slot.weather, self.base_params)
        )
        # Humid air from the start only slows drying (the model covers that);
        # once the laundry has dried a good part, it gets damp again instead.
        progressed = self.state.progress >= 0.3 * run.target
        if run.rewet_at is None and (raining or (humid and progressed)):
            run.rewet_at = now
