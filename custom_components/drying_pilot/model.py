# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

"""DryingPilot calculation core.

Plain Python without Home Assistant dependencies, so it can be tested offline
and calibrated against recorded data.

Model (based on Dalton's evaporation formula):

    rate [%/h] = (a + b * wind[km/h]) * VPD[hPa] + sun_gain * sun[0..1]

100 % corresponds to a normally loaded line or rotary dryer being dry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum

# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class Location(StrEnum):
    """Where the laundry is hanging."""

    LINE = "line"  # clothesline: sun helps, rain matters
    COVERED = "covered"  # covered: full shade, rain irrelevant


class LaundryType(StrEnum):
    """Laundry type, scales the drying target."""

    LIGHT = "light"
    NORMAL = "normal"
    HEAVY = "heavy"


class Category(StrEnum):
    """Drying suitability, derived from the rate."""

    NONE = "none"  # not drying
    SLOW = "slow"  # slow
    MODERATE = "moderate"  # Geht so
    GOOD = "good"  # Gut
    IDEAL = "ideal"  # Ideal


class Mode(StrEnum):
    """UI state of the tile."""

    INDOOR = "indoor"  # dry indoors (no window in sight)
    LATER = "later"  # next window later
    HANG_NOW = "hang_now"  # worth hanging out now
    DRYING = "drying"  # drying
    TIGHT = "tight"  # tight: target not reached in window
    BRING_IN = "bring_in"  # bring in
    DRY = "dry"  # dry
    PRE_DRY = "pre_dry"  # only a partial window: pre-dry outside
    PAUSED = "paused"  # laundry is out, but nothing dries right now


class BlockReason(StrEnum):
    """Why an hour is unsuitable for drying."""

    RAIN = "rain"
    HUMID = "humid"  # rewetting, air too humid
    SLOW = "slow"  # rate below minimum



# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelParams:
    """All tunable values. Defaults, to be calibrated."""

    # Penman-style rate, normalised at ref_temp:
    #   rate = k * [ (a + b * wind_factor * wind) * VPD * w_aero(T)
    #              + sun_gain * sun * w_rad(T) ]
    a: float = 1.6
    b: float = 0.12
    sun_gain: float = 12.0
    ref_temp: float = 15.0

    # calibration factors (learned per location)
    k: float = 1.0
    wind_factor: float = 1.0

    # category limits in %/h (lower bound of SLOW, MODERATE, GOOD, IDEAL)
    cat_slow: float = 5.0
    cat_moderate: float = 10.0
    cat_good: float = 17.0
    cat_ideal: float = 30.0

    # minimum rate for an hour to belong to a window
    min_rate: float = 5.0

    # rain criterion (clothesline only)
    rain_mm: float = 0.1
    rain_probability: float = 30.0

    # rewetting: textiles take up moisture above this relative humidity
    # (hysteresis: humid from rewet_rh, dry again at or below rewet_rh_exit)
    rewet_rh: float = 90.0
    rewet_rh_exit: float = 86.0
    # dew on the laundry: clear night and temperature close to the dew point
    dew_margin: float = 3.0
    clear_sky_cloud: float = 40.0

    # target per laundry type in %
    targets: dict[LaundryType, float] = field(
        default_factory=lambda: {
            LaundryType.LIGHT: 70.0,
            LaundryType.NORMAL: 100.0,
            LaundryType.HEAVY: 150.0,
        }
    )

    # local correction: time constant of the decaying offset
    correction_tau_h: float = 3.0

    # forecast sun: UV index that counts as "full sun"
    uv_full_sun: float = 6.0

    # pre-drying: partial windows of at least this length and gain count
    predry_min_hours: float = 3.0
    predry_min_gain: float = 30.0  # % of the target (drying potential)

    # lead time for "bring in" before rain
    bring_in_lead: timedelta = timedelta(hours=1)

    def target(self, laundry: LaundryType) -> float:
        return self.targets[laundry]


# --------------------------------------------------------------------------
# Data structures
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Weather:
    """Weather for a moment or an hour."""

    temperature: float  # °C
    humidity: float  # % rF
    wind_kmh: float = 0.0
    sun: float = 0.0  # 0..1
    rain_mm: float = 0.0
    rain_probability: float = 0.0  # %
    cloud: float | None = None  # % cloud coverage, if known


@dataclass(frozen=True)
class Slot:
    """One forecast hour."""

    start: datetime
    weather: Weather

    @property
    def end(self) -> datetime:
        return self.start + timedelta(hours=1)


@dataclass(frozen=True)
class Window:
    """Contiguous period in which drying is possible."""

    start: datetime
    end: datetime
    total: float  # accumulated progress in %
    sufficient: bool  # enough for the target
    dry_at: datetime | None  # time the target is reached


@dataclass(frozen=True)
class Estimate:
    """Projection for laundry that is hanging out."""

    dry_at: datetime | None  # None if the target is not reached within the window
    window_end: datetime | None  # None if no end within the horizon
    progress_at_window_end: float
    end_reason: BlockReason | None


# --------------------------------------------------------------------------
# Physics
# --------------------------------------------------------------------------


def saturation_vapor_pressure(temperature: float) -> float:
    """Saturation vapour pressure over water in hPa (Magnus, WMO constants)."""
    return 6.112 * math.exp(17.62 * temperature / (243.12 + temperature))


def vapor_pressure_deficit(temperature: float, humidity: float) -> float:
    """Vapour pressure deficit in hPa."""
    humidity = min(max(humidity, 0.0), 100.0)
    return saturation_vapor_pressure(temperature) * (1.0 - humidity / 100.0)


def dew_point(temperature: float, humidity: float) -> float:
    """Dew point in °C."""
    humidity = min(max(humidity, 1.0), 100.0)
    gamma = math.log(humidity / 100.0) + 17.62 * temperature / (243.12 + temperature)
    return 243.12 * gamma / (17.62 - gamma)


def humidity_from_dew_point(temperature: float, dew: float) -> float:
    """Relative humidity in % from temperature and dew point."""
    if dew >= temperature:
        return 100.0
    return 100.0 * saturation_vapor_pressure(dew) / saturation_vapor_pressure(temperature)


PSYCHROMETRIC_CONSTANT = 0.66  # hPa/K near sea level


def svp_slope(temperature: float) -> float:
    """Slope of the saturation vapour pressure curve in hPa/K."""
    return (
        saturation_vapor_pressure(temperature)
        * 17.62
        * 243.12
        / (243.12 + temperature) ** 2
    )


def penman_weights(temperature: float, ref_temp: float) -> tuple[float, float]:
    """Relative weights of the aerodynamic and radiative term (1.0 at ref_temp).

    From the Penman combination equation: the aerodynamic term scales with
    gamma / (delta + gamma), the radiative term with delta / (delta + gamma).
    """

    def split(t: float) -> tuple[float, float]:
        delta = svp_slope(t)
        total = delta + PSYCHROMETRIC_CONSTANT
        return PSYCHROMETRIC_CONSTANT / total, delta / total

    aero, rad = split(temperature)
    aero_ref, rad_ref = split(ref_temp)
    return aero / aero_ref, rad / rad_ref


def sun_from_pv(power_w: float | None, peak_w: float) -> float:
    """Sun factor 0..1 from current PV power."""
    if power_w is None or peak_w <= 0:
        return 0.0
    return min(max(power_w / peak_w, 0.0), 1.0)


def sun_from_forecast(
    uv_index: float | None, cloud_coverage: float | None, params: ModelParams
) -> float:
    """Sun factor 0..1 from forecast UV index and cloud coverage."""
    uv = max(uv_index or 0.0, 0.0)
    cloud = min(max(cloud_coverage or 0.0, 0.0), 100.0)
    base = min(uv / params.uv_full_sun, 1.0)
    return base * (1.0 - 0.7 * cloud / 100.0)


# --------------------------------------------------------------------------
# Rate and category
# --------------------------------------------------------------------------


def rate_terms(
    weather: Weather, location: Location, params: ModelParams
) -> tuple[float, float]:
    """Rate split into (P, Q) with rate = k * (P + wind_factor * Q).

    Linear in the calibration factors, which keeps the calibration cheap.
    """
    vpd = vapor_pressure_deficit(weather.temperature, weather.humidity)
    w_aero, w_rad = penman_weights(weather.temperature, params.ref_temp)
    sun = weather.sun if location is Location.LINE else 0.0
    p = params.a * vpd * w_aero + params.sun_gain * sun * w_rad
    # mass transfer grows with wind^0.7 (boundary layer), equal to the old
    # linear form at the reference wind speed
    wind = max(weather.wind_kmh, 0.0)
    q = params.b * WIND_REF**(1 - WIND_EXP) * wind**WIND_EXP * vpd * w_aero
    return p, q


WIND_EXP = 0.7
WIND_REF = 12.0  # km/h

# Two drying phases: constant rate while the surface is wet, then a falling
# rate (water has to come out of the fibres). X = remaining water fraction.
CRITICAL_MOISTURE = 0.3
DRY_MOISTURE = 0.05
_PHASE_TOTAL = (1 - CRITICAL_MOISTURE) + CRITICAL_MOISTURE * math.log(
    CRITICAL_MOISTURE / DRY_MOISTURE
)


def dryness(fraction: float) -> float:
    """Share of water removed (0..1) for an accumulated drying potential.

    `fraction` is progress / target (1.0 = dry). Early hours remove water fast,
    the last part slowly – the time to dry stays the same.
    """
    if fraction >= 1.0:
        return 1.0
    e = max(fraction, 0.0) * _PHASE_TOTAL
    if e <= 1 - CRITICAL_MOISTURE:
        x = 1 - e
    else:
        x = CRITICAL_MOISTURE * math.exp(-(e - (1 - CRITICAL_MOISTURE)) / CRITICAL_MOISTURE)
    return min((1 - x) / (1 - DRY_MOISTURE), 1.0)


# residual moisture after spinning (share of dry weight), typical values
SPIN_MOISTURE = [(400, 0.95), (800, 0.70), (1000, 0.62), (1200, 0.55), (1400, 0.50), (1600, 0.45), (2000, 0.40)]


def spin_factor(rpm: float) -> float:
    """Water at the start relative to 1400 rpm."""
    pts = SPIN_MOISTURE
    rpm = min(max(rpm, pts[0][0]), pts[-1][0])
    for (r1, m1), (r2, m2) in zip(pts, pts[1:]):
        if r1 <= rpm <= r2:
            m = m1 + (m2 - m1) * (rpm - r1) / (r2 - r1)
            return m / 0.50
    return 1.0


def drying_rate(weather: Weather, location: Location, params: ModelParams) -> float:
    """Drying rate in %/h (>= 0)."""
    p, q = rate_terms(weather, location, params)
    return max(params.k * (p + params.wind_factor * q), 0.0)


def category(rate: float, params: ModelParams) -> Category:
    if rate >= params.cat_ideal:
        return Category.IDEAL
    if rate >= params.cat_good:
        return Category.GOOD
    if rate >= params.cat_moderate:
        return Category.MODERATE
    if rate >= params.cat_slow:
        return Category.SLOW
    return Category.NONE


def is_raining(weather: Weather, params: ModelParams) -> bool:
    return (
        weather.rain_mm > params.rain_mm
        or weather.rain_probability > params.rain_probability
    )


def dew_risk(weather: Weather, params: ModelParams) -> bool:
    """Clear night with the air close to its dew point: dew forms on the laundry.

    Laundry radiates heat to a clear night sky and gets 2-4 K colder than the
    air, so dew forms before the air itself is saturated.
    """
    if weather.sun > 0.0 or weather.cloud is None:
        return False
    if weather.cloud >= params.clear_sky_cloud:
        return False
    spread = weather.temperature - dew_point(weather.temperature, weather.humidity)
    return spread < params.dew_margin


def humid_enter(weather: Weather, params: ModelParams) -> bool:
    """Conditions in which laundry starts taking up moisture again."""
    return weather.humidity >= params.rewet_rh or dew_risk(weather, params)


def humid_exit(weather: Weather, params: ModelParams) -> bool:
    """Conditions in which a humid phase is over (hysteresis)."""
    return weather.humidity <= params.rewet_rh_exit and not dew_risk(weather, params)


def next_humid_state(humid: bool, weather: Weather, params: ModelParams) -> bool:
    if humid:
        return not humid_exit(weather, params)
    return humid_enter(weather, params)


def block_reason(
    weather: Weather,
    location: Location,
    params: ModelParams,
    humid: bool | None = None,
) -> BlockReason | None:
    """Reason why this hour is unsuitable, or None.

    `humid` is the hysteresis state; without it the entry condition is used.
    """
    if location is Location.LINE and is_raining(weather, params):
        return BlockReason.RAIN
    if humid if humid is not None else humid_enter(weather, params):
        return BlockReason.HUMID
    if drying_rate(weather, location, params) < params.min_rate:
        return BlockReason.SLOW
    return None


# --------------------------------------------------------------------------
# Forecast preparation
# --------------------------------------------------------------------------


def apply_local_correction(
    slots: list[Slot],
    now: datetime,
    measured: Weather | None,
    params: ModelParams,
) -> list[Slot]:
    """Carry the sensor/forecast offset over to the coming hours.

    The difference in the current hour fades out with exp(-dt/tau).
    """
    if measured is None or not slots:
        return slots
    current = _slot_at(slots, now)
    if current is None:
        return slots
    d_t = measured.temperature - current.weather.temperature
    d_rh = measured.humidity - current.weather.humidity
    out: list[Slot] = []
    for slot in slots:
        dt_h = max((slot.start - current.start).total_seconds() / 3600.0, 0.0)
        k = math.exp(-dt_h / params.correction_tau_h)
        w = slot.weather
        out.append(
            replace(
                slot,
                weather=replace(
                    w,
                    temperature=w.temperature + k * d_t,
                    humidity=min(max(w.humidity + k * d_rh, 0.0), 100.0),
                ),
            )
        )
    return out


def slots_from_forecast(items: list[dict], params: ModelParams) -> list[Slot]:
    """Convert an HA hourly forecast (weather.get_forecasts) into slots."""
    slots: list[Slot] = []
    for item in items:
        try:
            start = datetime.fromisoformat(str(item["datetime"]))
            weather = Weather(
                temperature=float(item["temperature"]),
                humidity=float(item["humidity"]),
                wind_kmh=float(item.get("wind_speed") or 0.0),
                sun=sun_from_forecast(
                    item.get("uv_index"), item.get("cloud_coverage"), params
                ),
                rain_mm=float(item.get("precipitation") or 0.0),
                rain_probability=float(item.get("precipitation_probability") or 0.0),
                cloud=(
                    float(item["cloud_coverage"])
                    if item.get("cloud_coverage") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError):
            continue
        slots.append(Slot(start, weather))
    slots.sort(key=lambda s: s.start)
    return slots


def _slot_at(slots: list[Slot], moment: datetime) -> Slot | None:
    for slot in slots:
        if slot.start <= moment < slot.end:
            return slot
    return None


def _segments(
    slots: list[Slot], now: datetime, live: Weather | None
) -> list[tuple[datetime, datetime, Weather]]:
    """Segments from now: rest of current hour with live values, then forecast."""
    segs: list[tuple[datetime, datetime, Weather]] = []
    for slot in sorted(slots, key=lambda s: s.start):
        if slot.end <= now:
            continue
        start = max(slot.start, now)
        weather = slot.weather
        if live is not None and slot.start <= now < slot.end:
            # measured values for the current hour, keep rain from the forecast
            weather = replace(
                live,
                rain_mm=slot.weather.rain_mm,
                rain_probability=slot.weather.rain_probability,
                cloud=live.cloud if live.cloud is not None else slot.weather.cloud,
            )
        segs.append((start, slot.end, weather))
    if live is not None and (not segs or segs[0][0] > now):
        # no forecast for now: assume one hour of live values
        end = segs[0][0] if segs else now + timedelta(hours=1)
        segs.insert(0, (now, end, live))
    return segs


def _classified(
    slots: list[Slot],
    now: datetime,
    live: Weather | None,
    location: Location,
    params: ModelParams,
    humid_now: bool | None,
) -> list[tuple[datetime, datetime, Weather, BlockReason | None]]:
    """Segments from now with their block reason, humid state carried along."""
    out = []
    humid = humid_now
    for start, end, weather in _segments(slots, now, live):
        humid = (
            humid_enter(weather, params)
            if humid is None
            else next_humid_state(humid, weather, params)
        )
        out.append((start, end, weather, block_reason(weather, location, params, humid)))
    return out


RAIN_LIKELY_PROBABILITY = 60.0
RAIN_LIKELY_MM = 1.0
HUMID_LIGHT_OFFSET = 10.0


def rain_level(weather: Weather, params: ModelParams) -> str | None:
    """'likely', 'possible' or None - shown in the forecast strip."""
    if (
        weather.rain_probability > RAIN_LIKELY_PROBABILITY
        or weather.rain_mm >= RAIN_LIKELY_MM
    ):
        return "likely"
    if is_raining(weather, params):
        return "possible"
    return None


def humid_level(weather: Weather, humid: bool, params: ModelParams) -> int:
    """0..3: how strongly the air works against hanging laundry.

    3 = laundry takes up moisture (hysteresis state or dew),
    2 = air at the exit threshold (barely dries),
    1 = humid air, 0 = fine.
    """
    if humid or dew_risk(weather, params):
        return 3
    if weather.humidity >= params.rewet_rh_exit:
        return 2
    if weather.humidity >= params.rewet_rh - HUMID_LIGHT_OFFSET:
        return 1
    return 0


def forecast_series(
    slots: list[Slot],
    now: datetime,
    live: Weather | None,
    location: Location,
    params: ModelParams,
    humid_now: bool | None = None,
    target: float | None = None,
) -> list[dict]:
    """Hourly series for the card strip and charts (already locally corrected).

    With `target`, `pct` is the share of the drying need covered per hour (%/h).
    """
    out = []
    humid = humid_now
    for slot in slots:
        if slot.end <= now:
            continue
        weather = slot.weather
        humid = (
            humid_enter(weather, params)
            if humid is None
            else next_humid_state(humid, weather, params)
        )
        reason = block_reason(weather, location, params, humid)
        rate = drying_rate(weather, location, params)
        item = {
            "time": slot.start.isoformat(),
            "rate": round(rate, 1),
            "blocked": reason.value if reason else None,
            "rain": rain_level(weather, params),
            "humid": humid_level(weather, humid, params),
            "humidity": round(weather.humidity),
            "rain_mm": round(weather.rain_mm, 1),
            "rain_probability": round(weather.rain_probability),
        }
        if target:
            item["pct"] = round(rate / target * 100.0, 1)
        out.append(item)
    return out


# --------------------------------------------------------------------------
# Windows, "possible until", projection
# --------------------------------------------------------------------------


def find_windows(
    slots: list[Slot],
    now: datetime,
    location: Location,
    target: float,
    params: ModelParams,
    live: Weather | None = None,
    humid_now: bool | None = None,
) -> list[Window]:
    """All drying windows within the forecast horizon (incl. a running one)."""
    windows: list[Window] = []
    cur_start: datetime | None = None
    cur_end: datetime | None = None
    total = 0.0
    dry_at: datetime | None = None

    def close() -> None:
        if cur_start is not None and cur_end is not None:
            windows.append(
                Window(cur_start, cur_end, total, total >= target, dry_at)
            )

    for start, end, weather, reason in _classified(
        slots, now, live, location, params, humid_now
    ):
        if reason is None:
            if cur_start is None or cur_end != start:
                close()
                cur_start, total, dry_at = start, 0.0, None
            rate = drying_rate(weather, location, params)
            hours = (end - start).total_seconds() / 3600.0
            if dry_at is None and total + rate * hours >= target:
                dry_at = start + timedelta(hours=(target - total) / rate)
            total += rate * hours
            cur_end = end
        else:
            close()
            cur_start = cur_end = None
            total, dry_at = 0.0, None
    close()
    return windows


def possible_until(
    slots: list[Slot],
    now: datetime,
    location: Location,
    params: ModelParams,
    live: Weather | None = None,
    humid_now: bool | None = None,
) -> datetime | None:
    """End of the window running now, else None."""
    last_end: datetime | None = None
    for start, end, _weather, reason in _classified(
        slots, now, live, location, params, humid_now
    ):
        if last_end is None and start > now:
            return None  # no data for now: no window is running
        if reason is not None:
            return start if last_end is not None else None
        last_end = end
    return last_end


def next_window(
    slots: list[Slot],
    now: datetime,
    location: Location,
    target: float,
    params: ModelParams,
    live: Weather | None = None,
    humid_now: bool | None = None,
) -> Window | None:
    """First window that is enough for the target."""
    for window in find_windows(slots, now, location, target, params, live, humid_now):
        if window.sufficient:
            return window
    return None


def estimate(
    slots: list[Slot],
    now: datetime,
    progress: float,
    location: Location,
    target: float,
    params: ModelParams,
    live: Weather | None = None,
    humid_now: bool | None = None,
) -> Estimate:
    """Project from current progress to the target or the window end."""
    total = progress
    if total >= target:
        return Estimate(now, None, total, None)
    for start, end, weather, reason in _classified(
        slots, now, live, location, params, humid_now
    ):
        if reason is not None:
            return Estimate(None, start, total, reason)
        rate = drying_rate(weather, location, params)
        hours = (end - start).total_seconds() / 3600.0
        if total + rate * hours >= target:
            return Estimate(
                start + timedelta(hours=(target - total) / rate), None, target, None
            )
        total += rate * hours
    return Estimate(None, None, total, None)


def advance_progress(progress: float, rate: float, elapsed: timedelta) -> float:
    """Advance progress by the measured rate over the elapsed time."""
    return progress + rate * elapsed.total_seconds() / 3600.0


def next_rain(
    slots: list[Slot], now: datetime, params: ModelParams
) -> datetime | None:
    """Start of the next rain within the horizon."""
    for slot in sorted(slots, key=lambda s: s.start):
        if slot.end <= now:
            continue
        if is_raining(slot.weather, params):
            return max(slot.start, now)
    return None


# --------------------------------------------------------------------------
# Overall evaluation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Evaluation:
    """Everything the integration exposes as entities."""

    mode: Mode
    rate: float
    category: Category
    vpd: float
    dew_point: float | None
    possible_until: datetime | None
    next_window: Window | None
    progress: float | None
    target: float
    dry_at: datetime | None
    progress_at_window_end: float | None
    window_end: datetime | None
    bring_in: bool
    bring_in_reason: BlockReason | None
    next_rain: datetime | None
    windows: list[Window]
    predry_window: Window | None = None
    predry_windows: list[Window] = field(default_factory=list)


def predry_windows(
    windows: list[Window], now: datetime, target: float, params: ModelParams
) -> list[Window]:
    """Partial windows worth pre-drying in (long and productive enough)."""
    return [
        w
        for w in windows
        if not w.sufficient
        and w.end > now
        and (w.end - max(w.start, now)).total_seconds() / 3600 >= params.predry_min_hours
        and w.total >= params.predry_min_gain / 100 * target
    ]


def next_opportunity(ev: "Evaluation", now: datetime) -> tuple[str, Window | None]:
    """Earliest drying ('window') or pre-drying ('pre_dry') window not over yet."""
    candidates = [("pre_dry", w) for w in ev.predry_windows if w.end > now]
    if ev.next_window is not None and ev.next_window.end > now:
        candidates.append(("window", ev.next_window))
    if not candidates:
        return "none", None
    return min(candidates, key=lambda c: c[1].start)


def estimate_overall(
    slots: list[Slot],
    now: datetime,
    progress: float,
    location: Location,
    target: float,
    params: ModelParams,
    live: Weather | None = None,
    humid_now: bool | None = None,
) -> datetime | None:
    """When the laundry will be done if it stays out, pauses included."""
    total = progress
    for start, end, weather, reason in _classified(
        slots, now, live, location, params, humid_now
    ):
        if reason is not None:
            continue
        rate = drying_rate(weather, location, params)
        hours = (end - start).total_seconds() / 3600.0
        if rate > 0 and total + rate * hours >= target:
            return start + timedelta(hours=(target - total) / rate)
        total += rate * hours
    return None


def evaluate(
    slots: list[Slot],
    now: datetime,
    live: Weather | None,
    location: Location,
    laundry: LaundryType,
    params: ModelParams,
    hanging: bool = False,
    progress: float = 0.0,
    humid_now: bool | None = None,
) -> Evaluation:
    """Complete evaluation for one moment.

    `humid_now` is the debounced humid state from live measurements (with
    hysteresis and minimum duration); without it the entry condition of the
    current weather is used.
    """
    target = params.target(laundry)
    slots = apply_local_correction(slots, now, live, params)

    current = live
    if current is None:
        slot = _slot_at(slots, now)
        current = slot.weather if slot else None

    if humid_now is None and current is not None:
        humid_now = humid_enter(current, params)

    if current is not None:
        rate = drying_rate(current, location, params)
        vpd = vapor_pressure_deficit(current.temperature, current.humidity)
        dp = dew_point(current.temperature, current.humidity)
    else:
        rate, vpd, dp = 0.0, 0.0, None

    windows = find_windows(slots, now, location, target, params, live, humid_now)
    nxt = next(
        (w for w in windows if w.sufficient and w.end > now), None
    )
    until = possible_until(slots, now, location, params, live, humid_now)
    rain = next_rain(slots, now, params) if location is Location.LINE else None

    dry_at = window_end = None
    at_end: float | None = None
    bring_in = False
    bring_reason: BlockReason | None = None

    predry = predry_windows(windows, now, target, params)
    predry_window: Window | None = None

    if hanging:
        est = estimate(
            slots, now, progress, location, target, params, live, humid_now
        )
        dry_at, window_end = est.dry_at, est.window_end
        at_end = est.progress_at_window_end
        # nothing dries right now: the window is over or never started
        drying_now = until is not None and until > now
        if window_end is not None and window_end <= now:
            window_end = None
        if progress >= target:
            mode = Mode.DRY
        else:
            # bring in: rain approaching or air rewetting the laundry; humid air
            # only matters once the laundry has dried a good part
            if rain is not None and rain - now <= params.bring_in_lead:
                bring_in, bring_reason = True, BlockReason.RAIN
            elif humid_now and progress >= 0.3 * target:
                bring_in, bring_reason = True, BlockReason.HUMID
            if bring_in:
                mode = Mode.BRING_IN
            elif not drying_now and dry_at is None:
                mode = Mode.PAUSED
                dry_at = estimate_overall(
                    slots, now, progress, location, target, params, live, humid_now
                )
                window_end = None
            elif dry_at is None and window_end is not None:
                mode = Mode.TIGHT
            else:
                mode = Mode.DRYING
    else:
        current_window = windows[0] if windows and windows[0].start <= now else None
        if current_window is not None and current_window.sufficient:
            mode = Mode.HANG_NOW
        else:
            # the mode only describes the current moment: pre_dry while a
            # pre-drying window is running, later for anything still to come
            running = [w for w in predry if w.start <= now]
            if nxt is not None:
                mode = Mode.LATER
                predry_window = running[0] if running else None
            elif running:
                mode = Mode.PRE_DRY
                predry_window = running[0]
            elif predry:
                mode = Mode.LATER
                predry_window = predry[0]
            else:
                mode = Mode.INDOOR

    return Evaluation(
        mode=mode,
        rate=rate,
        category=category(rate, params),
        vpd=vpd,
        dew_point=dp,
        possible_until=until,
        next_window=nxt,
        progress=progress if hanging else None,
        target=target,
        dry_at=dry_at,
        progress_at_window_end=at_end,
        window_end=window_end,
        bring_in=bring_in,
        bring_in_reason=bring_reason,
        next_rain=rain,
        windows=windows,
        predry_window=predry_window,
        predry_windows=predry,
    )
