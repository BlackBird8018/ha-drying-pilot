# SPDX-FileCopyrightText: 2026 BlackBird8018
# SPDX-License-Identifier: Apache-2.0

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cdt.model import (
    BlockReason,
    Category,
    LaundryType,
    Location,
    Mode,
    ModelParams,
    Slot,
    Weather,
    advance_progress,
    category,
    dew_point,
    drying_rate,
    estimate,
    humidity_from_dew_point,
    evaluate,
    find_windows,
    possible_until,
    saturation_vapor_pressure,
    slots_from_forecast,
    vapor_pressure_deficit,
)

P = ModelParams()
UTC = timezone.utc
FIXTURES = Path(__file__).parent / "fixtures"


def make_slots(start: datetime, weathers: list[Weather]) -> list[Slot]:
    return [Slot(start + timedelta(hours=i), w) for i, w in enumerate(weathers)]


# ---------------------------------------------------------------- Physics


def test_saturation_vapor_pressure_reference_values():
    assert saturation_vapor_pressure(0) == pytest.approx(6.112, abs=0.01)
    assert saturation_vapor_pressure(20) == pytest.approx(23.37, abs=0.1)


def test_vpd_examples_from_concept():
    assert vapor_pressure_deficit(25, 80) == pytest.approx(6.3, abs=0.1)
    assert vapor_pressure_deficit(5, 80) == pytest.approx(1.7, abs=0.1)
    assert vapor_pressure_deficit(10, 100) == 0


def test_dew_point():
    assert dew_point(20, 50) == pytest.approx(9.3, abs=0.2)
    assert dew_point(10, 100) == pytest.approx(10, abs=0.01)


# ---------------------------------------------------------------- Rate


def test_rate_increases_with_wind_and_sun():
    calm = Weather(20, 60, wind_kmh=0)
    windy = Weather(20, 60, wind_kmh=20)
    sunny = Weather(20, 60, wind_kmh=0, sun=1)
    assert drying_rate(windy, Location.LINE, P) > drying_rate(calm, Location.LINE, P)
    assert drying_rate(sunny, Location.LINE, P) > drying_rate(calm, Location.LINE, P)


def test_covered_ignores_sun():
    sunny = Weather(20, 60, sun=1)
    shade = Weather(20, 60, sun=0)
    assert drying_rate(sunny, Location.COVERED, P) == drying_rate(
        shade, Location.COVERED, P
    )


@pytest.mark.parametrize(
    ("rate", "expected"),
    [
        (0, Category.NONE),
        (5, Category.SLOW),
        (12, Category.MODERATE),
        (20, Category.GOOD),
        (45, Category.IDEAL),
    ],
)
def test_category_boundaries(rate, expected):
    assert category(rate, P) is expected


def test_typical_summer_day_is_good_or_ideal():
    w = Weather(24, 50, wind_kmh=12, sun=0.6)
    assert category(drying_rate(w, Location.LINE, P), P) in (
        Category.GOOD,
        Category.IDEAL,
    )


def test_november_evening_does_not_dry():
    w = Weather(4.5, 90, wind_kmh=19)
    assert category(drying_rate(w, Location.LINE, P), P) is Category.NONE


# ---------------------------------------------------------------- Windows

T0 = datetime(2026, 7, 4, 8, 0, tzinfo=UTC)
GOOD = Weather(22, 50, wind_kmh=10, sun=0.5)
RAIN = Weather(16, 90, wind_kmh=10, rain_mm=1.5, rain_probability=80)
HUMID = Weather(12, 97, wind_kmh=2)


def test_window_ends_at_rain_on_line():
    slots = make_slots(T0, [GOOD] * 4 + [RAIN] * 2 + [GOOD] * 3)
    wins = find_windows(slots, T0, Location.LINE, 100, P)
    assert len(wins) == 2
    assert wins[0].start == T0
    assert wins[0].end == T0 + timedelta(hours=4)
    assert wins[1].start == T0 + timedelta(hours=6)


def test_rain_does_not_block_covered():
    rain_dry_air = Weather(18, 60, wind_kmh=10, rain_mm=0.5, rain_probability=70)
    slots = make_slots(T0, [GOOD] * 2 + [rain_dry_air] * 2 + [GOOD] * 2)
    wins = find_windows(slots, T0, Location.COVERED, 100, P)
    assert len(wins) == 1
    assert wins[0].end == T0 + timedelta(hours=6)


def test_window_sufficiency_and_dry_at():
    slots = make_slots(T0, [GOOD] * 8)
    rate = drying_rate(GOOD, Location.LINE, P)
    win = find_windows(slots, T0, Location.LINE, 100, P)[0]
    assert win.sufficient
    assert win.dry_at == T0 + timedelta(hours=100 / rate)


def test_short_window_insufficient():
    slots = make_slots(T0, [GOOD] + [RAIN] * 5)
    win = find_windows(slots, T0, Location.LINE, 100, P)[0]
    assert not win.sufficient
    assert win.dry_at is None


def test_partial_current_hour_counts_only_remaining_time():
    now = T0 + timedelta(minutes=30)
    slots = make_slots(T0, [GOOD] * 2)
    win = find_windows(slots, now, Location.LINE, 1000, P)[0]
    rate = drying_rate(GOOD, Location.LINE, P)
    assert win.start == now
    assert win.total == pytest.approx(rate * 1.5)


def test_possible_until():
    slots = make_slots(T0, [GOOD] * 3 + [HUMID] * 3)
    assert possible_until(slots, T0, Location.LINE, P) == T0 + timedelta(hours=3)
    assert possible_until(slots, T0 + timedelta(hours=4), Location.LINE, P) is None


def test_live_value_overrides_current_hour():
    slots = make_slots(T0, [GOOD] * 3)
    live_bad = Weather(10, 98, wind_kmh=0)
    assert possible_until(slots, T0, Location.LINE, P, live=live_bad) is None


# ---------------------------------------------------------------- Projection


def test_estimate_reaches_target():
    slots = make_slots(T0, [GOOD] * 10)
    rate = drying_rate(GOOD, Location.LINE, P)
    est = estimate(slots, T0, 40, Location.LINE, 100, P)
    assert est.dry_at == T0 + timedelta(hours=60 / rate)


def test_estimate_tight_when_window_closes():
    slots = make_slots(T0, [GOOD] * 2 + [RAIN] * 3)
    est = estimate(slots, T0, 0, Location.LINE, 150, P)
    assert est.dry_at is None
    assert est.window_end == T0 + timedelta(hours=2)
    assert est.end_reason is BlockReason.RAIN
    assert 0 < est.progress_at_window_end < 150


def test_advance_progress():
    assert advance_progress(10, 20, timedelta(minutes=30)) == pytest.approx(20)


# ---------------------------------------------------------------- Modes


def test_mode_hang_now_and_later_and_indoor():
    good_day = make_slots(T0, [GOOD] * 10)
    assert evaluate(good_day, T0, None, Location.LINE, LaundryType.NORMAL, P).mode is Mode.HANG_NOW

    later = make_slots(T0, [HUMID] * 4 + [GOOD] * 8)
    ev = evaluate(later, T0, None, Location.LINE, LaundryType.NORMAL, P)
    assert ev.mode is Mode.LATER
    assert ev.next_window.start == T0 + timedelta(hours=4)

    bad = make_slots(T0, [HUMID] * 24)
    assert evaluate(bad, T0, None, Location.LINE, LaundryType.NORMAL, P).mode is Mode.INDOOR


def test_mode_drying_tight_bring_in_dry():
    good_day = make_slots(T0, [GOOD] * 10)
    ev = evaluate(good_day, T0, None, Location.LINE, LaundryType.NORMAL, P, hanging=True, progress=30)
    assert ev.mode is Mode.DRYING
    assert ev.dry_at is not None

    closing = make_slots(T0, [GOOD] * 3 + [HUMID] * 5)
    ev = evaluate(closing, T0, None, Location.LINE, LaundryType.HEAVY, P, hanging=True, progress=0)
    assert ev.mode is Mode.TIGHT

    rain_soon = make_slots(T0, [GOOD] + [RAIN] * 3)
    ev = evaluate(rain_soon, T0 + timedelta(minutes=20), None, Location.LINE, LaundryType.NORMAL, P, hanging=True, progress=50)
    assert ev.mode is Mode.BRING_IN
    assert ev.bring_in_reason is BlockReason.RAIN

    ev = evaluate(good_day, T0, None, Location.LINE, LaundryType.NORMAL, P, hanging=True, progress=100)
    assert ev.mode is Mode.DRY


def test_covered_not_brought_in_for_rain():
    rain_dry_air = Weather(18, 60, wind_kmh=10, rain_mm=0.5, rain_probability=70)
    slots = make_slots(T0, [GOOD] + [rain_dry_air] * 5)
    ev = evaluate(slots, T0, None, Location.COVERED, LaundryType.NORMAL, P, hanging=True, progress=20)
    assert ev.mode is Mode.DRYING


def test_local_correction_applies_sensor_offset():
    slots = make_slots(T0, [GOOD] * 6)
    live_drier = Weather(22, 35, wind_kmh=10, sun=0.5)
    ev_plain = evaluate(slots, T0, None, Location.LINE, LaundryType.NORMAL, P)
    ev_corr = evaluate(slots, T0, live_drier, Location.LINE, LaundryType.NORMAL, P)
    assert ev_corr.rate > ev_plain.rate
    assert ev_corr.next_window.total > ev_plain.next_window.total


# ---------------------------------------------------------------- Real data


def test_real_forecast_november():
    items = json.loads((FIXTURES / "forecast_sample_november.json").read_text())
    slots = slots_from_forecast(items, P)
    assert len(slots) == 26
    now = datetime(2026, 11, 6, 15, 20, tzinfo=UTC)
    ev = evaluate(slots, now, None, Location.LINE, LaundryType.NORMAL, P)
    # 16:20 local time, 6 °C, 85 %, strong wind: slow at best, no full window,
    # but Saturday noon is good enough for pre-drying
    assert ev.category in (Category.NONE, Category.SLOW)
    # pre-drying only starts tomorrow: the mode shows the current moment
    assert ev.mode is Mode.LATER
    assert ev.predry_window.start.day == 7
    evening = evaluate(slots, now.replace(hour=18), None, Location.LINE, LaundryType.NORMAL, P)
    assert evening.category is Category.NONE
    # Saturday noon: slow, no sufficient window
    sat = next(s for s in slots if s.start.hour == 13 and s.start.day == 7)
    assert category(drying_rate(sat.weather, Location.LINE, P), P) in (
        Category.NONE,
        Category.SLOW,
    )


def test_humidity_from_dew_point_roundtrip():
    td = dew_point(12.0, 70.0)
    assert humidity_from_dew_point(12.0, td) == pytest.approx(70.0, abs=0.01)
    # warmer at the same dew point -> drier
    assert humidity_from_dew_point(18.0, td) < 70.0
    assert humidity_from_dew_point(5.0, 8.0) == 100.0


def test_two_phase_dryness_curve():
    from cdt.model import dryness
    assert dryness(0) == 0 and dryness(1.0) == 1.0
    assert dryness(0.5) > 0.6          # most water leaves early
    assert dryness(0.9) < 0.99         # the last part takes long
    values = [dryness(i / 20) for i in range(21)]
    assert values == sorted(values)


def test_wind_effect_saturates():
    calm, ref, storm = (drying_rate(Weather(20, 50, w), Location.COVERED, P) for w in (0, 12, 48))
    assert storm - ref < 3 * (ref - calm)   # 4x wind gives less than 4x wind effect


def test_spin_factor():
    from cdt.model import spin_factor
    assert spin_factor(1400) == pytest.approx(1.0)
    assert spin_factor(800) == pytest.approx(1.4)
    assert spin_factor(1600) < 1.0


def test_possible_until_none_without_running_window():
    later = make_slots(T0 + timedelta(hours=2), [HUMID] * 3)
    assert possible_until(later, T0, Location.LINE, P) is None
    gap_then_good = make_slots(T0 + timedelta(hours=2), [GOOD] * 3)
    assert possible_until(gap_then_good, T0, Location.LINE, P) is None


# ---------------------------------------------------------------- Pre-dry / paused
MEDIUM = Weather(14, 70, wind_kmh=8)   # dries, but slowly


def test_predry_mode_and_priority_of_full_window():
    partial = make_slots(T0, [MEDIUM] * 4 + [HUMID] * 20)
    ev = evaluate(partial, T0, None, Location.LINE, LaundryType.NORMAL, P)
    assert ev.mode is Mode.PRE_DRY
    assert ev.predry_window.start == T0 and not ev.predry_window.sufficient

    with_full_later = make_slots(T0, [MEDIUM] * 4 + [HUMID] * 4 + [GOOD] * 8)
    ev = evaluate(with_full_later, T0, None, Location.LINE, LaundryType.NORMAL, P)
    assert ev.mode is Mode.LATER                 # full window always wins
    assert ev.predry_window is not None          # but pre-drying now is mentioned


def test_future_predry_window_is_later_not_pre_dry():
    from cdt.model import next_opportunity

    future = make_slots(T0, [HUMID] * 3 + [MEDIUM] * 4 + [HUMID] * 20)
    ev = evaluate(future, T0, None, Location.LINE, LaundryType.NORMAL, P)
    assert ev.mode is Mode.LATER
    assert ev.next_window is None
    assert ev.predry_window.start == T0 + timedelta(hours=3)
    kind, w = next_opportunity(ev, T0)
    assert kind == "pre_dry" and w.start == T0 + timedelta(hours=3)

    # once the pre-drying window has started, the mode switches
    now = T0 + timedelta(hours=3)
    ev = evaluate(future, now, None, Location.LINE, LaundryType.NORMAL, P)
    assert ev.mode is Mode.PRE_DRY


def test_next_opportunity_prefers_earliest_window():
    from cdt.model import next_opportunity

    slots = make_slots(T0, [MEDIUM] * 4 + [HUMID] * 4 + [GOOD] * 8)
    ev = evaluate(slots, T0, None, Location.LINE, LaundryType.NORMAL, P)
    assert next_opportunity(ev, T0)[0] == "pre_dry"
    only_good = make_slots(T0, [HUMID] * 4 + [GOOD] * 8)
    ev = evaluate(only_good, T0, None, Location.LINE, LaundryType.NORMAL, P)
    kind, w = next_opportunity(ev, T0)
    assert kind == "window" and w is ev.next_window
    nothing = make_slots(T0, [HUMID] * 24)
    ev = evaluate(nothing, T0, None, Location.LINE, LaundryType.NORMAL, P)
    assert next_opportunity(ev, T0) == ("none", None)


def test_short_partial_window_is_not_suggested():
    short = make_slots(T0, [MEDIUM] * 2 + [HUMID] * 20)
    ev = evaluate(short, T0, None, Location.LINE, LaundryType.NORMAL, P)
    assert ev.mode is Mode.INDOOR


def test_paused_shows_no_past_times_and_overall_finish():
    now = T0 + timedelta(minutes=30)
    slots = make_slots(T0, [Weather(10, 85, wind_kmh=1)] * 3 + [GOOD] * 10)
    ev = evaluate(slots, now, None, Location.COVERED, LaundryType.NORMAL, P, hanging=True, progress=20)
    assert ev.mode is Mode.PAUSED
    assert ev.window_end is None
    assert ev.dry_at is not None and ev.dry_at > T0 + timedelta(hours=3)


def test_humid_air_with_little_progress_pauses_instead_of_bring_in():
    slots = make_slots(T0, [HUMID] * 6)
    ev = evaluate(slots, T0, None, Location.COVERED, LaundryType.NORMAL, P, hanging=True, progress=5)
    assert ev.mode is Mode.PAUSED
    ev = evaluate(slots, T0, None, Location.COVERED, LaundryType.NORMAL, P, hanging=True, progress=60)
    assert ev.mode is Mode.BRING_IN


# --------------------------------------------------------------------------
# Forecast strip series (0.10.0)
# --------------------------------------------------------------------------


def test_rain_level_tiers():
    from cdt.model import rain_level

    p = ModelParams()
    assert rain_level(Weather(15, 60), p) is None
    assert rain_level(Weather(15, 60, rain_probability=40), p) == "possible"
    assert rain_level(Weather(15, 60, rain_probability=70), p) == "likely"
    assert rain_level(Weather(15, 60, rain_mm=0.3), p) == "possible"
    assert rain_level(Weather(15, 60, rain_mm=1.2), p) == "likely"


def test_humid_level_tiers():
    from cdt.model import humid_level

    p = ModelParams()
    assert humid_level(Weather(15, 70), False, p) == 0
    assert humid_level(Weather(15, 82), False, p) == 1
    assert humid_level(Weather(15, 88), False, p) == 2
    assert humid_level(Weather(15, 88), True, p) == 3  # hysteresis still humid
    # clear night close to the dew point
    assert humid_level(Weather(5, 84, cloud=10), False, p) == 3


def test_forecast_series_fields_and_hysteresis():
    from cdt.model import forecast_series

    p = ModelParams()
    start = datetime(2026, 11, 7, 10, tzinfo=UTC)
    weathers = [
        Weather(12, 92),  # enters humid
        Weather(12, 88),  # still humid (hysteresis, exit at <= 86)
        Weather(12, 84),  # exits
        Weather(12, 60, rain_probability=80),
    ]
    series = forecast_series(make_slots(start, weathers), start, None, Location.LINE, p)
    assert [h["humid"] for h in series] == [3, 3, 1, 0]
    assert [h["rain"] for h in series] == [None, None, None, "likely"]
    assert series[3]["blocked"] == "rain"
    assert all({"time", "rate", "blocked", "rain", "humid"} <= h.keys() for h in series)


def test_forecast_series_skips_past_hours():
    from cdt.model import forecast_series

    start = datetime(2026, 11, 7, 10, tzinfo=UTC)
    slots = make_slots(start, [Weather(15, 60)] * 3)
    series = forecast_series(slots, start + timedelta(minutes=90), None, Location.LINE, ModelParams())
    assert len(series) == 2


def test_forecast_series_detail_fields():
    from cdt.model import forecast_series

    p = ModelParams()
    start = datetime(2026, 11, 7, 10, tzinfo=UTC)
    slots = make_slots(start, [Weather(18, 55, wind_kmh=10, rain_mm=1.24, rain_probability=72.4)])
    (h,) = forecast_series(slots, start, None, Location.COVERED, p, target=50.0)
    assert h["humidity"] == 55
    assert h["rain_mm"] == 1.2
    assert h["rain_probability"] == 72
    assert h["pct"] == round(h["rate"] / 50.0 * 100.0, 1) or abs(h["pct"] - h["rate"] * 2) < 0.2
    # without a target no pct
    (h2,) = forecast_series(slots, start, None, Location.COVERED, p)
    assert "pct" not in h2
